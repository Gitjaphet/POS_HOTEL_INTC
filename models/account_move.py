from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _is_hotel_invoice(self):
        self.ensure_one()
        if self.env["pos.hotel.folio.charge"].search_count([("x_invoice_id", "=", self.id)], limit=1):
            return True
        return bool(self.line_ids.sale_line_ids.order_id.order_line.filtered("x_is_a_room_offer"))

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