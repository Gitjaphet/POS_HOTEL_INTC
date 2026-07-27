from odoo import api, fields, models


class PosHotelCheckoutOverride(models.TransientModel):
    _name = "pos.hotel.checkout.override"
    _description = "Dérogation de check-out avec solde impayé"

    sale_order_id = fields.Many2one("sale.order", required=True, ondelete="cascade")
    amount_due_at_override = fields.Monetary(
        string="Montant dû",
        related="sale_order_id.x_folio_total_due",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(related="sale_order_id.currency_id")
    reason = fields.Text(string="Raison", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.env["pos.hotel.checkout.override.log"].create({
            "sale_order_id": self.sale_order_id.id,
            "forced_by_user_id": self.env.user.id,
            "reason": self.reason,
            "amount_due_at_override": self.sale_order_id.x_folio_total_due,
        })
        return self.sale_order_id._force_checkout_bypass()