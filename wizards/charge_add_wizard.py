from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelChargeAddWizard(models.TransientModel):
    _name = "pos.hotel.charge.add.wizard"
    _description = "Ajout manuel d'un extra directement côté hôtel (hors POS)"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Folio",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
    )
    available_slot_ids = fields.Many2many(
        "planning.slot",
        compute="_compute_available_slot_ids",
    )
    planning_slot_id = fields.Many2one(
        "planning.slot",
        string="Chambre",
        required=True,
        domain="[('id', 'in', available_slot_ids)]",
    )
    name = fields.Char(
        string="Description",
        required=True,
    )
    amount = fields.Monetary(
        string="Montant",
        required=True,
    )

    @api.depends("sale_order_id")
    def _compute_available_slot_ids(self):
        for wizard in self:
            wizard.available_slot_ids = wizard.sale_order_id.x_room_stay_slot_ids.filtered(
                lambda s: s.x_stay_status == 'checked_in'
            )

    def action_confirm(self):
        self.ensure_one()
        if self.currency_id.is_zero(self.amount) or self.amount < 0:
            raise UserError("Le montant doit être supérieur à zéro.")
        slot = self.planning_slot_id
        self.env['pos.hotel.folio.charge'].create({
            "name": self.name,
            "sale_order_id": self.sale_order_id.id,
            "sale_order_line_id": slot.sale_line_id.id,
            "x_room_resource_id": slot.resource_id.id,
            "partner_id": slot.sale_line_id.order_id.partner_id.id,
            "amount": self.amount,
            "payment_status": "due",
        })
        return {"type": "ir.actions.act_window_close"}