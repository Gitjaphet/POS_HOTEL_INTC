from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelChargeAddWizard(models.TransientModel):
    _name = "pos.hotel.charge.add.wizard"
    _description = "Ajout manuel d'un ou plusieurs extras directement côté hôtel (hors POS)"

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
    line_ids = fields.One2many(
        "pos.hotel.charge.add.wizard.line",
        "wizard_id",
        string="Extras",
    )

    @api.depends("sale_order_id")
    def _compute_available_slot_ids(self):
        for wizard in self:
            wizard.available_slot_ids = wizard.sale_order_id.x_room_stay_slot_ids.filtered(
                lambda s: s.x_stay_status == 'checked_in'
            )

    def action_confirm(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError("Ajoutez au moins un extra.")
        slot = self.planning_slot_id
        for line in self.line_ids:
            if self.currency_id.is_zero(line.subtotal) or line.subtotal < 0:
                raise UserError("Le montant doit être supérieur à zéro pour chaque extra.")
            name = line.product_id.display_name
            if line.quantity > 1:
                name = f"{name} x{int(line.quantity)}"
            self.env['pos.hotel.folio.charge']._create_manual_charge({
                "name": name,
                "sale_order_id": self.sale_order_id.id,
                "sale_order_line_id": slot.sale_line_id.id,
                "x_room_resource_id": slot.resource_id.id,
                "partner_id": slot.sale_line_id.order_id.partner_id.id,
                "amount": line.subtotal,
                "payment_status": "due",
            })
        return {"type": "ir.actions.act_window_close"}


class PosHotelChargeAddWizardLine(models.TransientModel):
    _name = "pos.hotel.charge.add.wizard.line"
    _description = "Ligne d'extra du wizard d'ajout manuel"

    wizard_id = fields.Many2one(
        "pos.hotel.charge.add.wizard",
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(
        related="wizard_id.currency_id",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Extra",
        required=True,
        domain="[('available_in_pos', '=', True)]",
    )
    quantity = fields.Float(
        string="Qté",
        default=1,
        required=True,
    )
    unit_price = fields.Monetary(
        string="Prix unitaire",
        required=True,
    )
    subtotal = fields.Monetary(
        string="Sous-total",
        compute="_compute_subtotal",
        store=True,
    )

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.unit_price = self.product_id.lst_price