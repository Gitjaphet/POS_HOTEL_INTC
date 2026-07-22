from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x_folio_charge_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Transferts POS",
    )