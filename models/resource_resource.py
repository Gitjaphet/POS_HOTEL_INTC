from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "pos.load.mixin"]

    x_current_partner_id = fields.Many2one(
        "res.partner",
        string="Client en cours (POS Hotel)",
        compute="_compute_x_current_partner_id",
    )

    def _x_current_checked_in_slot(self):
        """Séjour ENREGISTRÉ de la chambre (Arrivée faite, Départ pas fait),
        le plus récent, SANS condition de date de fin : un client en retard
        de départ est toujours dans la chambre et consomme. Règle unique pour
        la liste « Transfert Chambre » du POS (x_current_partner_id) et pour
        le rattachement des consommations (pos.order)."""
        self.ensure_one()
        return self.env["planning.slot"].sudo().search([
            ("resource_id", "=", self.id),
            ("x_stay_status", "=", "checked_in"),
            ("sale_line_id", "!=", False),
            ("start_datetime", "<=", fields.Datetime.now()),
        ], order="start_datetime desc", limit=1)

    @api.depends()
    def _compute_x_current_partner_id(self):
        for resource in self:
            slot = resource._x_current_checked_in_slot()
            resource.x_current_partner_id = slot.sale_line_id.order_id.partner_id

    @api.model
    def _get_room_resource_domain(self):
        """Domaine des ressources qui sont des chambres physiques.

        Source de vérité unique : tout appelant (chargement POS, statistiques
        du planning hôtel) passe par ici plutôt que de redéfinir le domaine,
        pour qu'un changement de critère ne laisse jamais deux définitions
        divergentes dans le module.
        """
        return [("default_role_id.x_is_a_room_offer", "=", True)]

    def _sync_occupancy_from_slots(self):
        """Recalcule x_occupancy (champ booking_engine) depuis nos créneaux.

        Source de vérité : planning.slot.x_stay_status, chambre par chambre —
        jamais l'état global de la commande (rental_status), qui marquait
        toutes les chambres d'une commande d'un coup.

        - créneau checked_in, départ après aujourd'hui -> occupied
          (stayover conservé s'il a été posé par la tâche de minuit)
        - créneau checked_in, départ aujourd'hui ou dépassé -> due_out
          (un check-out oublié reste visible, jamais libéré en silence)
        - aucun créneau checked_in -> vacant

        Le jour s'évalue dans le fuseau de la chambre, pas en UTC.
        N'écrit que si la valeur change (idempotent, évite les conflits
        de mise à jour concurrente).
        """
        rooms = self.filtered_domain(self._get_room_resource_domain())
        if not rooms:
            return
        now = fields.Datetime.now()
        slots = self.env["planning.slot"].sudo().search([
            ("resource_id", "in", rooms.ids),
            ("x_stay_status", "=", "checked_in"),
            ("start_datetime", "<=", now),
        ], order="start_datetime desc")
        for room in rooms:
            slot = slots.filtered(lambda s: s.resource_id == room)[:1]
            if not slot:
                target = "vacant"
            else:
                tz = pytz.timezone(room.tz or "UTC")
                today = pytz.utc.localize(now).astimezone(tz).date()
                end_day = (
                    slot.end_datetime
                    and pytz.utc.localize(slot.end_datetime).astimezone(tz).date()
                )
                if end_day and end_day > today:
                    target = (
                        room.x_occupancy
                        if room.x_occupancy in ("occupied", "stayover")
                        else "occupied"
                    )
                else:
                    target = "due_out"
            if room.x_occupancy != target:
                room.sudo().x_occupancy = target

    # ------------------------------------------------------------------
    # Ménage : balai du planning
    # ------------------------------------------------------------------

    @api.model
    def _x_hk_clean_stages(self):
        """Étapes de ménage « fait » : Propre et Prêt (xmlid booking_engine,
        jamais par id : les ids changent d'une base à l'autre)."""
        stages = self.env["project.task.type"]
        for xmlid in ("booking_engine.project_task_type_17", "booking_engine.project_task_type_18"):
            stage = self.env.ref(xmlid, raise_if_not_found=False)
            if stage:
                stages |= stage
        return stages

    @staticmethod
    def _x_local_day_start_utc(tz_name, now, days=0):
        """Minuit local (fuseau tz_name) du jour de `now`, décalé de `days`
        jours, exprimé en UTC naïf (format des Datetime Odoo)."""
        tz = pytz.timezone(tz_name or "UTC")
        today_local = pytz.utc.localize(now).astimezone(tz).date()
        midnight = tz.localize(datetime.combine(today_local + timedelta(days=days), time.min))
        return midnight.astimezone(pytz.UTC).replace(tzinfo=None)

    @staticmethod
    def _x_local_day_label(slot_datetime, tz_name):
        tz = pytz.timezone(tz_name or "UTC")
        return pytz.utc.localize(slot_datetime).astimezone(tz).strftime("%d/%m")

    def _x_rooms_reserved_today(self):
        """Chambres promises à un client CONFIRMÉ pas encore arrivé (séjour
        pending) dont le séjour touche la journée d'aujourd'hui, dans le
        fuseau de chaque chambre. Une réservation pour plus tard n'empêche
        pas la chambre d'être disponible aujourd'hui."""
        now = fields.Datetime.now()
        candidates = self.env["planning.slot"].sudo().search([
            ("resource_id", "in", self.ids),
            ("x_stay_status", "=", "pending"),
            ("sale_line_id", "!=", False),
            ("end_datetime", ">", now),
        ])
        reserved = self.env["resource.resource"]
        for slot in candidates:
            day_stop_utc = self._x_local_day_start_utc(slot.resource_id.tz, now, days=1)
            if slot.start_datetime and slot.start_datetime < day_stop_utc:
                reserved |= slot.resource_id
        return reserved

    def _x_late_departure_slots(self):
        """Dernier séjour ENREGISTRÉ (checked_in) dont la date de départ est
        dépassée, par chambre : départ non effectué (client parti sans
        passer à la réception, ou Départ oublié). {id chambre: créneau}"""
        slots = self.env["planning.slot"].sudo().search([
            ("resource_id", "in", self.ids),
            ("x_stay_status", "=", "checked_in"),
            ("sale_line_id", "!=", False),
            ("end_datetime", "<", fields.Datetime.now()),
        ], order="end_datetime desc")
        late = {}
        for slot in slots:
            late.setdefault(slot.resource_id.id, slot)
        return late

    def _x_late_arrival_slots(self):
        """Réservations CONFIRMÉES dont le JOUR d'arrivée est passé (fuseau de
        la chambre) sans Arrivée : possible no-show. Le jour J n'est jamais
        signalé (arrivées du soir). Plus ancienne d'abord. {id chambre: créneau}"""
        now = fields.Datetime.now()
        slots = self.env["planning.slot"].sudo().search([
            ("resource_id", "in", self.ids),
            ("x_stay_status", "=", "pending"),
            ("sale_line_id.order_id.state", "=", "sale"),
            ("start_datetime", "<", now),
        ], order="start_datetime asc")
        late = {}
        for slot in slots:
            today_start_utc = self._x_local_day_start_utc(slot.resource_id.tz, now)
            if slot.start_datetime < today_start_utc:
                late.setdefault(slot.resource_id.id, slot)
        return late

    @api.model
    def get_hotel_broom_states(self):
        """Indicateur de chaque chambre dans le planning (un seul appel),
        une seule icône par chambre, par ordre de priorité :

        1. départ dépassé sans Départ : 'late' (réveil, clic = réservation)
        2. client en séjour (occupied / stayover / due_out) : rien
        3. ménage du jour ni Propre ni Prêt : 'dirty' (balai rouge) — passe
           AVANT le no-show : une chambre sale n'accueille personne ; une
           fois nettoyée, le sablier apparaît aussitôt
        4. jour d'arrivée passé sans Arrivée : 'noshow' (sablier, clic =
           réservation)
        5. propre mais réservée par un client confirmé attendu aujourd'hui :
           rien (la chambre n'est pas disponible pour un autre client)
        6. propre, libre, sans réservation aujourd'hui : 'clean' (balai vert)

        :return: {id de chambre: {'state': ..., 'title': texte de la bulle}}
        """
        clean = self._x_hk_clean_stages()
        rooms = self.search(self._get_room_resource_domain())
        reserved = rooms._x_rooms_reserved_today()
        late = rooms._x_late_departure_slots()
        noshow = rooms._x_late_arrival_slots()
        states = {}
        for room in rooms:
            slot = late.get(room.id)
            if slot:
                states[room.id] = {
                    "state": "late",
                    "title": "Départ prévu le %s (%s), non effectué : cliquer pour ouvrir la réservation" % (
                        self._x_local_day_label(slot.end_datetime, room.tz),
                        slot.sale_line_id.order_id.name,
                    ),
                }
                continue
            if room.x_occupancy in ("occupied", "stayover", "due_out"):
                continue
            task = room.x_ongoing_task_id
            if task and task.stage_id not in clean:
                states[room.id] = {
                    "state": "dirty",
                    "title": "À nettoyer : cliquer quand la chambre est propre",
                }
                continue
            slot = noshow.get(room.id)
            if slot:
                states[room.id] = {
                    "state": "noshow",
                    "title": "Arrivée prévue le %s (%s), non effectuée : possible no-show. Cliquer pour ouvrir la réservation" % (
                        self._x_local_day_label(slot.start_datetime, room.tz),
                        slot.sale_line_id.order_id.name,
                    ),
                }
                continue
            if room not in reserved:
                states[room.id] = {
                    "state": "clean",
                    "title": "Chambre propre et prête",
                }
        return states

    def action_hotel_open_late_folio(self):
        """Clic sur le réveil (départ en retard) ou le sablier (arrivée en
        retard) : ouvre la réservation concernée avec la fiche hôtel. Même
        priorité que get_hotel_broom_states : le départ d'abord."""
        self.ensure_one()
        slot = self._x_late_departure_slots().get(self.id) or self._x_late_arrival_slots().get(self.id)
        if not slot:
            return False
        return slot._x_hotel_folio_action(slot.sale_line_id.order_id)

    def action_hotel_broom_clean(self):
        """Clic sur le balai rouge : le ménage du jour passe à « Propre ».
        booking_engine enchaîne sur « Prêt » ; pos_hotel_amenities, s'il est
        installé, débite le kit à ce moment-là."""
        clean_stage = self.env.ref("booking_engine.project_task_type_17", raise_if_not_found=False)
        if not clean_stage:
            return False
        clean = self._x_hk_clean_stages()
        for room in self:
            task = room.x_ongoing_task_id
            if task and task.stage_id not in clean:
                task.stage_id = clean_stage
        return True

    def _x_prepare_checkout_cleaning(self, partner=False):
        """Au départ du client : la chambre est à nettoyer tout de suite.

        Réutilise le ménage non fait du jour (créé par la tâche de minuit)
        en le marquant « Départ », sinon en crée un avec les mêmes champs que
        la tâche de minuit de booking_engine. Respecte le réglage « ménage
        au départ » du type de chambre (x_has_checkout_cleaning).
        """
        project = self.env["project.project"].sudo().search(
            [("x_is_house_keeping_project", "=", True)], limit=1
        )
        if not project:
            return
        clean = self._x_hk_clean_stages()
        for room in self.filtered_domain(self._get_room_resource_domain()):
            if not room.default_role_id.x_has_checkout_cleaning:
                continue
            task = room.x_ongoing_task_id
            if task and task.stage_id not in clean:
                if task.x_cleaning != "checkout":
                    task.sudo().x_cleaning = "checkout"
                continue
            self.env["project.task"].sudo().create({
                "name": "HK " + room.name,
                "project_id": project.id,
                "partner_id": partner.id if partner else False,
                "description": "Ménage de départ créé au check-out.",
                "date_deadline": fields.Datetime.now(),
                "x_resource_id": room.id,
                "x_cleaning": "checkout",
                "user_ids": [(5, 0)],
            })

    @api.model
    def _load_pos_data_domain(self, data, config):
        return self._get_room_resource_domain()

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "x_occupant_ids", "x_current_partner_id"]

    @api.depends_context('hotel_show_room_type')
    def _compute_display_name(self):
        # « 401 (Chambre Suite) » uniquement sous le contexte
        # hotel_show_room_type (fenêtre Changer de chambre) ; ailleurs
        # (planning, POS, factures) le nom reste « 401 ».
        super()._compute_display_name()
        if self.env.context.get('hotel_show_room_type'):
            # Même type que le planning : type par défaut, sinon le premier.
            for resource in self.filtered('role_ids'):
                role = resource.sudo().default_role_id or resource.role_ids[:1]
                resource.display_name = "%s (%s)" % (resource.name, role.name)
