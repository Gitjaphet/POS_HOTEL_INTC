from odoo import api, models


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "pos.load.mixin"]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("default_role_id.x_is_a_room_offer", "=", True)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "x_occupant_ids"]