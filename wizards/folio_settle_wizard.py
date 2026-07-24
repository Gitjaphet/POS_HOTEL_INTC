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
    charge_ids = fields.Many2many(
        "pos.hotel.folio.charge",
        string="Charges à régler",
        domain="[('sale_order_id', '=', sale_order_id), ('payment_status', '=', 'due')]",
    )
    total_amount = fields.Monetary(
        string="Montant total",
        compute="_compute_total_amount",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal de paiement",
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Mode de paiement",
        domain="[('journal_id', '=', journal_id)]",
    )

    @api.depends("charge_ids", "charge_ids.amount_net")
    def _compute_total_amount(self):
        for wizard in self:
            wizard.total_amount = sum(wizard.charge_ids.mapped("amount_net"))

    def action_confirm_settle(self):
        self.ensure_one()
        if not self.charge_ids:
            raise UserError("Sélectionnez au moins une charge à régler.")
        return self.charge_ids.action_settle(
            journal_id=self.journal_id.id,
            payment_method_line_id=self.payment_method_line_id.id or None,
        )