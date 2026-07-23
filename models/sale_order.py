from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x_folio_charge_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Transferts POS",
    )
    x_folio_charge_normal_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Consommations POS",
        domain=[("is_refund", "=", False)],
    )
    x_folio_charge_refund_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Remboursements",
        domain=[("is_refund", "=", True)],
    )
    x_folio_total_paid = fields.Monetary(
        string="Total Extra Payé",
        compute="_compute_folio_totals",
        help="Somme des consommations déjà payées, au POS ou réglées ensuite par le réceptionniste.",
    )
    x_folio_total_due = fields.Monetary(
        string="Total Extra Dû",
        compute="_compute_folio_totals",
        help="Somme des consommations encore dues au réceptionniste.",
    )

    @api.depends(
        "x_folio_charge_normal_ids.amount_net",
        "x_folio_charge_normal_ids.payment_status",
    )
    def _compute_folio_totals(self):
        for order in self:
            charges = order.x_folio_charge_normal_ids
            order.x_folio_total_paid = sum(
                charges.filtered(lambda c: c.payment_status in ("paid_pos", "settled")).mapped("amount_net")
            )
            order.x_folio_total_due = sum(
                charges.filtered(lambda c: c.payment_status == "due").mapped("amount_net")
            )