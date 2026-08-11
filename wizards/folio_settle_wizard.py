from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelFolioSettleWizard(models.TransientModel):
    _name = "pos.hotel.folio.settle.wizard"
    _description = "Règlement des charges dues d'un folio"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Folio",
        required=True,
        readonly=True,
    )
    is_service = fields.Boolean(
        string="Règlement de services",
        default=False,
        help="Si coché, ne règle que les services dus (compte 411300). "
             "Sinon, règle les extras dus (compte 411200).",
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
    )
    total_due = fields.Monetary(
        string="Total dû",
        compute="_compute_total_due",
    )
    amount = fields.Monetary(
        string="Montant à régler",
        required=True,
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Mode de paiement",
        required=True,
        domain="[('payment_type', '=', 'inbound')]",
    )

    @api.depends("sale_order_id", "is_service")
    def _compute_total_due(self):
        for wizard in self:
            wizard.total_due = (
                wizard.sale_order_id.x_folio_total_due_service
                if wizard.is_service
                else wizard.sale_order_id.x_folio_total_due
            )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if res.get("sale_order_id") and "amount" in fields_list:
            sale_order = self.env["sale.order"].browse(res["sale_order_id"])
            is_service = res.get("is_service", False)
            res["amount"] = (
                sale_order.x_folio_total_due_service if is_service else sale_order.x_folio_total_due
            )
        return res

    def action_confirm_settle(self):
        self.ensure_one()
        if self.currency_id.is_zero(self.amount) or self.amount < 0:
            raise UserError("Le montant à régler doit être supérieur à zéro.")
        return self.env["pos.hotel.folio.charge"]._settle_amount_for_order(
            self.sale_order_id, self.amount, self.payment_method_line_id.id, is_service=self.is_service
        )