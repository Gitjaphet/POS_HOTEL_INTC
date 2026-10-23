from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _is_hotel_invoice(self):
        self.ensure_one()
        if self.env["pos.hotel.folio.charge"].search_count([("x_invoice_id", "=", self.id)], limit=1):
            return True
        return bool(self.line_ids.sale_line_ids.order_id.order_line.filtered("x_is_a_room_offer"))

    def _post(self, soft=True):
        """À la confirmation d'une facture client : compensation des
        consommations (extras/services) qu'elle contient et qui n'en ont pas
        encore (voir folio_charge_offset.py). Jamais au brouillon."""
        posted = super()._post(soft)
        invoices = posted.filtered(lambda m: m.move_type == "out_invoice")
        if invoices:
            Charge = self.env["pos.hotel.folio.charge"]
            for invoice in invoices:
                charges = Charge.search([
                    ("x_invoice_id", "=", invoice.id),
                    ("x_invoice_offset_move_id", "=", False),
                ])
                if charges:
                    charges._x_post_invoice_offset(invoice)
        return posted

    def _x_hotel_cancel_offsets(self, reason):
        """Facture client annulée ou entièrement extournée : ses
        consommations redeviennent facturables, leurs compensations sont
        contrepassées (folio_charge_offset._x_cancel_invoice_offset)."""
        Charge = self.env["pos.hotel.folio.charge"]
        for invoice in self.filtered(lambda m: m.move_type == "out_invoice"):
            if invoice.state != "cancel" and invoice.payment_state != "reversed":
                continue
            charges = Charge.search([
                ("x_invoice_id", "=", invoice.id),
                ("x_invoice_offset_move_id", "!=", False),
            ])
            if charges:
                charges._x_cancel_invoice_offset(f"{reason} {invoice.name}")

    def _reverse_moves(self, default_values_list=None, cancel=False):
        reverse_moves = super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)
        self._x_hotel_cancel_offsets("facture extournée")
        return reverse_moves

    def button_cancel(self):
        result = super().button_cancel()
        self._x_hotel_cancel_offsets("facture annulée")
        return result

    def _reconcile_reversed_moves(self, reverse_moves, move_reverse_cancel):
        result = super()._reconcile_reversed_moves(reverse_moves, move_reverse_cancel)
        for move, reverse_move in zip(self, reverse_moves):
            if not move._is_hotel_invoice():
                continue
            m_lines = move.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
            r_lines = reverse_move.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
            if not m_lines or not r_lines:
                continue
            (m_lines | r_lines).filtered("reconciled").remove_move_reconcile()
            (m_lines | r_lines).reconcile()
        return result
