from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _reconcile_reversed_moves(self, reverse_moves, move_reverse_cancel):
        result = super()._reconcile_reversed_moves(reverse_moves, move_reverse_cancel)
        Charge = self.env["pos.hotel.folio.charge"]
        for move, reverse_move in zip(self, reverse_moves):
            if not Charge.search_count([("x_invoice_id", "=", move.id)], limit=1):
                continue
            move_receivable = move.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable" and not l.currency_id
            )
            reversed_receivable = reverse_move.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable" and not l.currency_id
            )
            for account in move_receivable.account_id:
                m_lines = move_receivable.filtered(lambda l: l.account_id == account)
                r_lines = reversed_receivable.filtered(lambda l: l.account_id == account)
                if not r_lines:
                    continue
                reconciled = m_lines.filtered("reconciled")
                if reconciled:
                    reconciled.remove_move_reconcile()
                (m_lines | r_lines).reconcile()
        return result