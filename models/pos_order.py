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
        if self.env["pos.hotel.folio.charge"].search_count([("pos_order_id", "=", self.id)]):
            return  # déjà traité, on évite le doublon

        sale_orders = self.partner_id.x_ongoing_bookings.x_ongoing_booking.sale_order_id
        if not sale_orders:
            return
        sale_order = sale_orders[:1]

        # Ratio de la commande payé via "Transfert Chambre" (mécanisme B) vs
        # payé normalement au POS (mécanisme A). Gère le paiement mixte (split) :
        # ex. client paie une partie au POS, une partie plus tard au réceptionniste.
        room_charge_amount = sum(
            self.payment_ids.filtered(lambda p: p.payment_method_id.is_room_charge).mapped("amount")
        )
        total_amount = self.amount_total
        ratio = (room_charge_amount / total_amount) if total_amount else 0.0

        folio_charge = self.env["pos.hotel.folio.charge"]
        for line in self.lines:
            if not line.price_subtotal_incl:
                continue
            if ratio <= 0:
                folio_charge._create_from_pos_order_line(self, sale_order, line, "paid_pos")
            elif ratio >= 1:
                folio_charge._create_from_pos_order_line(self, sale_order, line, "due")
            else:
                due_amount = line.price_subtotal_incl * ratio
                paid_amount = line.price_subtotal_incl - due_amount
                folio_charge._create_from_pos_order_line(self, sale_order, line, "due", amount=due_amount)
                folio_charge._create_from_pos_order_line(self, sale_order, line, "paid_pos", amount=paid_amount)