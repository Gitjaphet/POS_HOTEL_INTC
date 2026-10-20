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
