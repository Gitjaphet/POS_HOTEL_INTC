from odoo import fields, models


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