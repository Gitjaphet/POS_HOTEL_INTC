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

    @api.depends()
    def _compute_x_current_partner_id(self):
        now = fields.Datetime.now()
        Slot = self.env["planning.slot"]
        for resource in self:
            slot = Slot.search([
                ("resource_id", "=", resource.id),
                ("x_stay_status", "=", "checked_in"),
                ("start_datetime", "<=", now),
                ("end_datetime", ">=", now),
            ], limit=1)
            resource.x_current_partner_id = slot.sale_line_id.order_id.partner_id if slot and slot.sale_line_id else False

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

    @api.model
    def get_hotel_broom_states(self):
        """État du balai de chaque chambre, pour le planning (un seul appel).

        - client en séjour (occupied / stayover / due_out) : pas de balai
        - ménage du jour (tâche en cours) ni Propre ni Prêt : 'dirty' (rouge)
        - sinon : 'clean' (vert)

        :return: {id de chambre: 'dirty' | 'clean'}
        """
        clean = self._x_hk_clean_stages()
        states = {}
        for room in self.search(self._get_room_resource_domain()):
            if room.x_occupancy in ("occupied", "stayover", "due_out"):
                continue
            task = room.x_ongoing_task_id
            states[room.id] = "dirty" if task and task.stage_id not in clean else "clean"
        return states

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
