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
        if not self.partner_id:
            return

        sale_orders = self.partner_id.x_ongoing_bookings.x_ongoing_booking.sale_order_id
        if not sale_orders:
            return
        sale_order = sale_orders[:1]

        room_charge_payments = self.payment_ids.filtered(
            lambda p: p.payment_method_id.is_room_charge
        )
        # Mécanisme B : paiement via "Transfert Chambre" -> statut "due"
        # Mécanisme A : paiement classique mais client occupant -> statut "paid_pos"
        payment_status = "due" if room_charge_payments else "paid_pos"

        folio_charge = self.env["pos.hotel.folio.charge"]
        for line in self.lines:
            if not line.price_subtotal_incl:
                continue
            folio_charge._create_from_pos_order_line(self, sale_order, line, payment_status)