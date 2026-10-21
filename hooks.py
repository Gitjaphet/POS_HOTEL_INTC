def post_init_hook(env):
    for company in env["res.company"].search([]):
        env["pos.payment.method"]._ensure_room_charge_method(company)
        env["pos.payment.method"]._ensure_extras_income_account(company)
        env["pos.payment.method"]._ensure_service_charge_account(company)
        env["pos.payment.method"]._ensure_service_income_account(company)
    _fix_room_calendars(env)
    _fix_booking_engine_order_form_view(env)
    _disable_room_hours_automation(env)
    _disable_room_occupancy_automation(env)
    _sync_all_room_occupancy(env)
    _fix_ongoing_task_compute(env)
    _apply_booking_source_defaults(env)
    _apply_hotel_labels(env)


def _fix_room_calendars(env):
    calendar = env.ref("booking_engine.calendar_1", raise_if_not_found=False)
    if not calendar:
        return
    rooms = env["resource.resource"].search([("role_ids", "!=", False)])
    rooms.filtered(lambda r: r.calendar_id != calendar).write({"calendar_id": calendar.id})


def _fix_booking_engine_order_form_view(env):
    action = env.ref("booking_engine.booking_engine_rooms_order_action", raise_if_not_found=False)
    hotel_view = env.ref("POS_HOTEL_INTC.sale_order_primary_view_pos_hotel_intc", raise_if_not_found=False)
    if not action or not hotel_view:
        return
    action_view = env["ir.actions.act_window.view"].search([
        ("act_window_id", "=", action.id),
        ("view_mode", "=", "form"),
    ])
    if action_view:
        action_view.view_id = hotel_view.id


def _disable_room_hours_automation(env):
    """Désactive l'action d'automatisation Studio "Ajuster les horaires des
    créneaux" (base.automation sur planning.slot).

    CONFLIT AVEC POS_HOTEL_INTC : cette règle forçait systématiquement
    start_datetime/end_datetime des planning.slot à pickup_time/return_time
    (ex. 18:00/09:00, récurrence "Nights"), en écrasant toute heure de
    début/fin de séjour personnalisée saisie via x_room_start_date/
    x_room_return_date (Planning). C'est la cause racine confirmée du bug de
    désynchro Planning <-> commande (investigation du 22/08/2026).

    Repérage par contenu du code plutôt que par ID technique : cette règle
    est créée via Studio (base.automation), donc son ID varie d'une base à
    l'autre. On la retrouve par signature (modèle planning.slot + code
    manipulant pickup_time ET return_time), pour ne jamais viser la mauvaise
    règle sur une autre base.
    """
    rules = env["base.automation"].with_context(active_test=False).search([
        ("model_name", "in", ["planning.slot", "sale.order"]),
    ])
    for rule in rules:
        for action in rule.action_server_ids:
            code = action.code or ""
            if "pickup_time" in code and "return_time" in code:
                if "DÉSACTIVÉ AUTOMATIQUEMENT PAR LE MODULE" not in code:
                    marker = (
                        "# ⚠️ DÉSACTIVÉ AUTOMATIQUEMENT PAR LE MODULE POS_HOTEL_INTC.\n"
                        "# Cette action forçait systématiquement start_datetime/end_datetime à\n"
                        "# pickup_time/return_time (récurrence 'Nights'), en écrasant toute heure\n"
                        "# de début/fin de séjour personnalisée saisie dans POS_HOTEL_INTC\n"
                        "# (champs x_room_start_date/x_room_return_date). Cause racine confirmée\n"
                        "# du bug de désynchro Planning <-> commande (investigation du 22/08/2026).\n"
                        "# Règle désactivée (active=False) par hooks.py::_disable_room_hours_automation.\n"
                        "# Code laissé ci-dessous pour référence uniquement, jamais exécuté.\n\n"
                    )
                    action.write({"code": marker + code})
                if rule.active:
                    rule.write({"active": False})


def _disable_room_occupancy_automation(env):
    """Désactive les automatisations booking_engine "Ménage : lors de
    l'enregistrement" / "Ménage : lors du départ" (base.automation sur
    sale.order, déclenchées par rental_status).

    CONFLIT AVEC POS_HOTEL_INTC : elles écrivaient x_occupancy sur TOUTES les
    chambres d'une commande selon l'état global de celle-ci — un seul
    check-in marquait toutes les chambres « Occupé », une chambre partie
    restait « Occupé » tant que la commande entière n'était pas rendue, et
    une annulation (créneaux supprimés) ne libérait jamais rien. Le statut
    est désormais calculé chambre par chambre depuis planning.slot
    .x_stay_status par resource.resource._sync_occupancy_from_slots()
    (investigation du 20/10/2026).

    Repérage par signature (modèle sale.order + code écrivant x_occupancy),
    jamais par ID : l'ID varie d'une base à l'autre.
    """
    rules = env["base.automation"].with_context(active_test=False).search([
        ("model_name", "=", "sale.order"),
    ])
    for rule in rules:
        for action in rule.action_server_ids:
            code = action.code or ""
            if "x_occupancy" in code:
                if "DÉSACTIVÉ AUTOMATIQUEMENT PAR LE MODULE" not in code:
                    marker = (
                        "# ⚠️ DÉSACTIVÉ AUTOMATIQUEMENT PAR LE MODULE POS_HOTEL_INTC.\n"
                        "# Cette action écrivait x_occupancy sur toutes les chambres d'une\n"
                        "# commande selon son rental_status global (statuts faux en\n"
                        "# multi-chambres, jamais libérés à l'annulation). Remplacée par\n"
                        "# resource.resource._sync_occupancy_from_slots(), chambre par chambre\n"
                        "# (investigation du 20/10/2026).\n"
                        "# Règle désactivée (active=False) par hooks.py::_disable_room_occupancy_automation.\n"
                        "# Code laissé ci-dessous pour référence uniquement, jamais exécuté.\n\n"
                    )
                    action.write({"code": marker + code})
                if rule.active:
                    rule.write({"active": False})


def _sync_all_room_occupancy(env):
    """Recalcule le statut d'occupation de toutes les chambres depuis les
    créneaux. Rattrape les statuts faux hérités des automatisations
    désactivées ci-dessus — à appeler APRÈS _disable_room_occupancy_automation."""
    Resource = env["resource.resource"]
    Resource.search(Resource._get_room_resource_domain())._sync_occupancy_from_slots()


ONGOING_TASK_MARKER = "MODIFIÉ PAR POS_HOTEL_INTC"
ONGOING_TASK_COMPUTE = (
    "# MODIFIÉ PAR POS_HOTEL_INTC (21/10/2026) : la tâche en cours est le\n"
    "# ménage le PLUS RÉCENT de la chambre, même déjà « Prêt ». La formule\n"
    "# d'origine gardait la plus ANCIENNE tâche non terminée : la fiche chambre\n"
    "# ouvrait un ménage de plusieurs semaines et « Étape de ménage » modifiait\n"
    "# ce vieux ménage au lieu de celui du jour.\n"
    "for record in self:\n"
    "    record['x_ongoing_task_id'] = record.x_task_ids.sorted('id')[-1:].id or False\n"
)


def _fix_ongoing_task_compute(env):
    """Remplace la formule de booking_engine du champ calculé
    resource.resource.x_ongoing_task_id (« Tâche en cours »).

    Repérage par signature (formule contenant is_closed) et marqueur
    idempotent ; puis recalcul immédiat de toutes les chambres (Étape de
    ménage, related stocké, suit automatiquement).
    """
    field = env["ir.model.fields"].search([
        ("model", "=", "resource.resource"),
        ("name", "=", "x_ongoing_task_id"),
    ], limit=1)
    if not field or ONGOING_TASK_MARKER in (field.compute or ""):
        return
    if "is_closed" not in (field.compute or ""):
        return  # formule inconnue : on ne touche à rien
    field.write({"compute": ONGOING_TASK_COMPUTE})
    Resource = env["resource.resource"]
    rooms = Resource.search([("x_task_ids", "!=", False)])
    env.add_to_compute(Resource._fields["x_ongoing_task_id"], rooms)
    env.flush_all()


BOOKING_SOURCE_DEFAULTS = {
    "POS_HOTEL_INTC.utm_source_booking_com": ("B", "#003580"),
    "POS_HOTEL_INTC.utm_source_website": ("W", "#6610F2"),
    "POS_HOTEL_INTC.utm_source_direct": ("D", "#198754"),
    "POS_HOTEL_INTC.utm_source_walk_in": ("WI", "#6C757D"),
    "POS_HOTEL_INTC.utm_source_agency": ("A", "#E8590C"),
}
# Sources ajoutées à la main par l'hôtel (sans xmlid) : reconnues par leur nom.
BOOKING_SOURCE_BY_NAME = {
    "expedia": ("E", "#FFC72C"),
    "airbnb": ("AB", "#FF5A5F"),
}


def _apply_booking_source_defaults(env):
    """Code et couleur d'étiquette par défaut des sources de réservation.
    Ne remplit que les sources SANS code : un réglage modifié par l'hôtel
    n'est jamais écrasé. Source inconnue : deux premières lettres, gris."""
    for xmlid, (code, color) in BOOKING_SOURCE_DEFAULTS.items():
        source = env.ref(xmlid, raise_if_not_found=False)
        if source and not source.x_booking_code:
            source.write({"x_booking_code": code, "x_booking_color": color})
    for source in env["utm.source"].search([
        ("x_is_booking_source", "=", True),
        ("x_booking_code", "=", False),
    ]):
        name = (source.name or "").strip().lower()
        code, color = next(
            ((c, col) for key, (c, col) in BOOKING_SOURCE_BY_NAME.items() if key in name),
            ((source.name or "?")[:2].upper(), "#6C757D"),
        )
        source.write({"x_booking_code": code, "x_booking_color": color})


def _apply_hotel_labels(env):
    """Applique les noms hôteliers des menus de booking_engine (i18n/fr.po)
    en ÉCRASANT les traductions existantes.

    Sans overwrite, Odoo ne remplace jamais une traduction déjà présente :
    celle de booking_engine (« Offres », « Ressources »...), chargée avant
    nous, gardait la priorité. Seuls les termes de notre fr.po sont
    concernés (investigation du 21/10/2026).
    """
    env["ir.module.module"].search([("name", "=", "POS_HOTEL_INTC")])._update_translations(overwrite=True)
