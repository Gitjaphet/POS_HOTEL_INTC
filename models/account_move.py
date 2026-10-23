from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _is_hotel_invoice(self):
        self.ensure_one()
        if self.env["pos.hotel.folio.charge"].search_count([("x_invoice_id", "=", self.id)], limit=1):
            return True
        return bool(self.line_ids.sale_line_ids.order_id.order_line.filtered("x_is_a_room_offer"))

    def _post(self, soft=True):
        """À la confirmation d'une facture client :
        - compensation des consommations DUES qu'elle contient et qui n'en
          ont pas encore (folio_charge_offset.py) ;
        - écriture « Réglé pendant le séjour » pour les consommations déjà
          réglées qu'elle contient (account_move_prepaid.py).
        Jamais au brouillon."""
        posted = super()._post(soft)
        invoices = posted.filtered(lambda m: m.move_type == "out_invoice")
        if invoices:
            Charge = self.env["pos.hotel.folio.charge"]
            for invoice in invoices:
                charges = Charge.search([
                    ("x_invoice_id", "=", invoice.id),
                    ("payment_status", "=", "due"),
                    ("x_invoice_offset_move_id", "=", False),
                ])
                if charges:
                    charges._x_post_invoice_offset(invoice)
            invoices._x_post_prepaid_entry()
        # Avoir confirmé : la facture qu'il extourne l'est-elle maintenant
        # entièrement ? (Odoo 19 crée l'avoir en brouillon ; le
        # rapprochement avec la facture a lieu à sa confirmation.)
        refunds = posted.filtered(lambda m: m.move_type == "out_refund" and m.reversed_entry_id)
        if refunds:
            refunds.reversed_entry_id._x_hotel_cancel_offsets("avoir sur")
        return posted

    def _x_hotel_cancel_offsets(self, reason):
        """Facture client annulée ou entièrement extournée : ses
        consommations redeviennent facturables ; les compensations sont
        contrepassées (folio_charge_offset._x_cancel_invoice_offset), ainsi
        que l'écriture « Réglé pendant le séjour »
        (account_move_prepaid._x_cancel_prepaid_entry)."""
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
            invoice._x_cancel_prepaid_entry(f"{reason} {invoice.name}")

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
