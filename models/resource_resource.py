from odoo import api, fields, models


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "pos.load.mixin"]

    x_current_partner_id = fields.Many2one(
        "res.partner",
        string="Client en cours (POS Hotel)",
        compute="_compute_x_current_partner_id",
    )

    @api.depends("x_ongoing_booking.start_datetime", "x_ongoing_booking.end_datetime", "x_ongoing_booking.sale_line_id.order_id.partner_id")
    def _compute_x_current_partner_id(self):
        now = fields.Datetime.now()
        for resource in self:
            slot = resource.x_ongoing_booking.filtered(
                lambda s: s.start_datetime <= now <= s.end_datetime
            )[:1]
            resource.x_current_partner_id = slot.sale_line_id.order_id.partner_id if slot and slot.sale_line_id else False

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("default_role_id.x_is_a_room_offer", "=", True)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "x_occupant_ids", "x_current_partner_id"]