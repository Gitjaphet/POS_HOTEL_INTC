from odoo import api, models


class PosOrder(models.Model):
    """Garde-fou du POS : un article déjà sur une facture active ne se
    rembourse pas depuis la caisse.

    Le remboursement créerait une consommation négative pendant que la
    facture continue de réclamer l'article, et laisserait un crédit
    411200 orphelin (night audit bloqué). Le serveur ne peut pas refuser
    un ticket déjà validé à la caisse : le POS l'interroge AVANT la
    validation (payment_screen.js, validateOrder) et bloque si cette
    méthode renvoie quelque chose (23/10/2026)."""
    _inherit = "pos.order"

    @api.model
    def x_hotel_refund_invoiced_lines(self, line_ids):
        """`line_ids` : lignes d'ORIGINE remboursées. Renvoie les
        consommations de ces lignes figurant sur une facture active. Un
        article de formule (combo) est ramené à sa formule, qui porte la
        consommation."""
        ids = [i for i in (line_ids or []) if isinstance(i, int)]
        lines = self.env["pos.order.line"].browse(ids).exists()
        lines |= lines.combo_parent_id
        if not lines:
            return []
        charges = self.env["pos.hotel.folio.charge"].search([
            ("pos_order_line_id", "in", lines.ids),
            ("is_refund", "=", False),
            ("x_invoice_is_active", "=", True),
        ])
        return [
            {
                "name": charge.name,
                "invoice": charge.x_invoice_id.name or "brouillon",
                "partner": (charge.partner_id or charge.sale_order_id.partner_id).name or "",
            }
            for charge in charges
        ]
