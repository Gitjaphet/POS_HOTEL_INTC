from odoo import api, fields, models


class PosHotelOrderCancelWizard(models.TransientModel):
    _name = "pos.hotel.order.cancel.wizard"
    _description = "Annulation de commande avec motif obligatoire"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Commande",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
    )
    due_amount = fields.Monetary(
        string="Montant dû sur ce folio",
        compute="_compute_charge_amounts",
        currency_field="currency_id",
    )
    settled_amount = fields.Monetary(
        string="Montant déjà réglé sur ce folio (à rembourser)",
        compute="_compute_charge_amounts",
        currency_field="currency_id",
    )
    cancel_due_debt = fields.Boolean(
        string="Annuler aussi la dette due sur ce folio",
    )
    refund_settled_charges = fields.Boolean(
        string="Rembourser aussi les extras déjà réglés sur ce folio",
    )
    refund_payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Mode de remboursement",
        domain="[('payment_type', '=', 'outbound')]",
    )
    reason = fields.Text(
        string="Motif d'annulation",
        required=True,
    )

    @api.depends("sale_order_id")
    def _compute_charge_amounts(self):
        for wizard in self:
            charges = wizard.sale_order_id.x_folio_charge_normal_ids + wizard.sale_order_id.x_folio_charge_service_ids
            due_charges = charges.filtered(
                lambda c: c.payment_status == "due" and not c.x_invoice_is_active
            )
            wizard.due_amount = sum(due_charges.mapped("amount_net"))
            settled_charges = charges.filtered(lambda c: c.payment_status == "settled")
            wizard.settled_amount = sum(settled_charges.mapped("amount_net"))

    def action_confirm_cancel(self):
        self.ensure_one()
        order = self.sale_order_id
        order.action_cancel_folio_charges(
            self.cancel_due_debt, self.refund_settled_charges,
            self.refund_payment_method_line_id.id
        )
        order._action_cancel()
        order.message_post(
            body=f"Commande annulée. Motif : {self.reason}"
        )
        return {"type": "ir.actions.act_window_close"}