from odoo import api, fields, models


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    x_include_pos_extras = fields.Boolean(
        string="Inclure les extras dus",
        help="Si coché, les consommations POS transférées au folio et encore dues "
             "seront ajoutées comme lignes de la facture (compte 411200 conservé), "
             "en plus des lignes de chambres. Uniquement disponible pour une facture "
             "normale (pas un acompte).",
    )
    x_has_due_pos_extras = fields.Boolean(
        string="A des extras dus",
        compute="_compute_x_has_due_pos_extras",
        help="Technique : détermine si la case 'Inclure les extras dus' doit être visible.",
    )

    @api.depends("sale_order_ids")
    def _compute_x_has_due_pos_extras(self):
        for wizard in self:
            wizard.x_has_due_pos_extras = bool(
                wizard.sale_order_ids.x_folio_charge_normal_ids.filtered(
                    lambda c: c.payment_status == "due"
                )
            )