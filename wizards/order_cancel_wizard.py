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
    reason = fields.Text(
        string="Motif d'annulation",
        required=True,
    )

    def action_confirm_cancel(self):
        self.ensure_one()
        order = self.sale_order_id
        order._action_cancel()
        order.message_post(
            body=f"Commande annulée. Motif : {self.reason}"
        )
        return {"type": "ir.actions.act_window_close"}