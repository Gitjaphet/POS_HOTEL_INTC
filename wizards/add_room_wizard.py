from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PosHotelAddRoomWizard(models.TransientModel):
    _name = "pos.hotel.add.room.wizard"
    _description = "Ajout d'une chambre supplémentaire sur une ligne confirmée"

    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne de commande",
        required=True,
        readonly=True,
    )
    available_resource_ids = fields.Many2many(
        "resource.resource",
        compute="_compute_available_resource_ids",
        string="Chambres disponibles",
    )
    resource_id = fields.Many2one(
        "resource.resource",
        string="Chambre à ajouter",
        required=True,
        domain="[('id', 'in', available_resource_ids)]",
    )

    @api.depends('sale_order_line_id')
    def _compute_available_resource_ids(self):
        for wizard in self:
            if wizard.sale_order_line_id:
                wizard.available_resource_ids = wizard.sale_order_line_id._get_free_room_resources()
            else:
                wizard.available_resource_ids = False

    def action_confirm_add_room(self):
        self.ensure_one()
        sol = self.sale_order_line_id
        sol.with_context(x_forced_room_resource_id=self.resource_id.id).write({
            'product_uom_qty': sol.product_uom_qty + 1,
        })
        return {"type": "ir.actions.act_window_close"}