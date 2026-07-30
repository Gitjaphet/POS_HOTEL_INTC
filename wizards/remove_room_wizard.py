from odoo import api, fields, models


class PosHotelRemoveRoomWizard(models.TransientModel):
    _name = "pos.hotel.remove.room.wizard"
    _description = "Retrait d'une chambre d'une ligne confirmée, avec motif obligatoire"

    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne de commande",
        required=True,
        readonly=True,
    )
    resource_id = fields.Many2one(
        "resource.resource",
        string="Chambre à retirer",
        required=True,
        domain="[('id', 'in', available_resource_ids)]",
    )
    available_resource_ids = fields.Many2many(
        "resource.resource",
        compute="_compute_available_resource_ids",
        string="Chambres sur cette ligne",
    )
    due_amount = fields.Monetary(
        string="Montant dû sur cette chambre",
        compute="_compute_charge_amounts",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        related="sale_order_line_id.currency_id",
    )
    cancel_due_debt = fields.Boolean(
        string="Annuler aussi la dette due sur cette chambre",
    )
    reason = fields.Text(
        string="Motif du retrait",
        required=True,
    )

    @api.depends("sale_order_line_id")
    def _compute_available_resource_ids(self):
        for wizard in self:
            wizard.available_resource_ids = wizard.sale_order_line_id.x_room_resource_ids

    @api.depends("sale_order_line_id", "resource_id")
    def _compute_charge_amounts(self):
        for wizard in self:
            charges = self.env["pos.hotel.folio.charge"].search([
                ("sale_order_line_id", "=", wizard.sale_order_line_id.id),
                ("x_room_resource_id", "=", wizard.resource_id.id),
                ("payment_status", "=", "due"),
            ])
            wizard.due_amount = sum(charges.mapped("amount_net"))

    def action_confirm_remove_room(self):
        self.ensure_one()
        self.sale_order_line_id.action_remove_room(
            self.resource_id.id, self.reason, self.cancel_due_debt
        )
        return {"type": "ir.actions.act_window_close"}