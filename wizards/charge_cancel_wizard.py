from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelChargeCancelWizard(models.TransientModel):
    _name = "pos.hotel.charge.cancel.wizard"
    _description = "Annulation d'un extra encore dû, avec motif obligatoire"

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
        string="Montant dû",
        currency_field="currency_id",
    )
    reason = fields.Text(
        string="Motif d'annulation",
        required=True,
    )

    def action_confirm(self):
        self.ensure_one()
        charge = self.charge_id
        if charge.payment_status != 'due':
            raise UserError(
                "Cet extra n'est plus dû (déjà réglé, payé ou déjà annulé) — "
                "impossible de l'annuler ainsi."
            )
        charge._transition_to_cancelled(reason=self.reason)
        
        charge.sale_order_id.message_post(
            body=f"Extra annulé : {charge.name} ({charge.amount_net} "
                 f"{charge.currency_id.symbol}). Motif : {self.reason}"
        )
        return {"type": "ir.actions.act_window_close"}