from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _reconcile_reversed_moves(self, reverse_moves, move_reverse_cancel):
        result = super()._reconcile_reversed_moves(reverse_moves, move_reverse_cancel)
        Charge = self.env["pos.hotel.folio.charge"]
        for move, reverse_move in zip(self, reverse_moves):
            if not Charge.search_count([("x_invoice_id", "=", move.id)], limit=1):
                continue
            m_lines = move.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
            r_lines = reverse_move.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
            if not m_lines or not r_lines:
                continue
            (m_lines | r_lines).filtered("reconciled").remove_move_reconcile()
            (m_lines | r_lines).reconcile()
        return result