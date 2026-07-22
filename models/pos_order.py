from odoo import models


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _process_saved_order(self, draft):
        order_id = super()._process_saved_order(draft)
        if not draft and self.state != "cancel":
            self._create_room_charge_folio_lines()
        return order_id

    def _create_room_charge_folio_lines(self):
        self.ensure_one()
        room_charge_payments = self.payment_ids.filtered(
            lambda p: p.payment_method_id.is_room_charge
        )
        if not room_charge_payments or not self.partner_id:
            return

        sale_orders = self.partner_id.x_ongoing_bookings.x_ongoing_booking.sale_order_id
        if not sale_orders:
            return
        sale_order = sale_orders[:1]

        folio_charge = self.env["pos.hotel.folio.charge"]
        for line in self.lines:
            folio_charge._create_from_pos_order_line(self, sale_order, line, "due")
