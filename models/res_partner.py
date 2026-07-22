from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    x_room_charge_due = fields.Monetary(
        compute="_compute_room_charge_due",
        currency_field="currency_id",
    )

    def _compute_room_charge_due(self):
        for partner in self:
            orders = partner.x_ongoing_bookings.x_ongoing_booking.sale_order_id
            charges = orders.x_folio_charge_ids.filtered(
                lambda c: c.payment_status == "due"
            )
            partner.x_room_charge_due = sum(charges.mapped("amount"))

    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + ["x_ongoing_bookings", "x_room_charge_due"]