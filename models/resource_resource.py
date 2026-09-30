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
            for resource in self.filtered('role_ids'):
                resource.display_name = "%s (%s)" % (
                    resource.name, ", ".join(resource.role_ids.mapped('name')),
                )
