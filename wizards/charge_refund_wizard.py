from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelChargeRefundWizard(models.TransientModel):
    _name = "pos.hotel.charge.refund.wizard"
    _description = "Remboursement d'un extra réglé (compte 411200)"

    charge_id = fields.Many2one(
        "pos.hotel.folio.charge",
        string="Extra",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="charge_id.currency_id",
    )
    amount_net = fields.Monetary(
        related="charge_id.amount_net",
        string="Montant à rembourser",
        currency_field="currency_id",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Mode de paiement du remboursement",
        required=True,
        domain="[('payment_type', '=', 'outbound')]",
    )

    def action_confirm(self):
        self.ensure_one()
        charge = self.charge_id
        if charge.payment_status != 'settled':
            raise UserError(
                "Seul un extra au statut 'Réglé' peut être remboursé ainsi."
            )
        charge.action_refund_settled(self.payment_method_line_id.id)
        return {"type": "ir.actions.act_window_close"}