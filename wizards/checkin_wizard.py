from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelCheckinWizard(models.TransientModel):
    _name = "pos.hotel.checkin.wizard"
    _description = "Enregistrement / Départ par chambre"

    order_id = fields.Many2one(
        "sale.order",
        string="Commande",
        required=True,
        ondelete="cascade",
    )
    status = fields.Selection(
        [
            ("checkin", "Enregistrement"),
            ("checkout", "Départ"),
        ],
        string="Type d'opération",
        required=True,
    )
    line_ids = fields.One2many(
        "pos.hotel.checkin.wizard.line",
        "wizard_id",
        string="Chambres",
    )

    def action_confirm(self):
        self.ensure_one()
        selected = self.line_ids.filtered("selected")
        if not selected:
            raise UserError("Sélectionnez au moins une chambre.")
        for line in selected:
            slot = line.planning_slot_id
            order_line = slot.sale_line_id
            if self.status == "checkin":
                slot.write({
                    "x_stay_status": "checked_in",
                    "x_checked_in_at": fields.Datetime.now(),
                })
                order_line.update({"qty_delivered": order_line.qty_delivered + 1})
            else:
                slot.write({
                    "x_stay_status": "checked_out",
                    "x_checked_out_at": fields.Datetime.now(),
                })
                order_line.update({"qty_returned": order_line.qty_returned + 1})
        return {"type": "ir.actions.act_window_close"}


class PosHotelCheckinWizardLine(models.TransientModel):
    _name = "pos.hotel.checkin.wizard.line"
    _description = "Ligne chambre du wizard d'enregistrement/départ"

    wizard_id = fields.Many2one(
        "pos.hotel.checkin.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    planning_slot_id = fields.Many2one(
        "planning.slot",
        string="Séjour (chambre)",
        required=True,
        ondelete="cascade",
    )
    resource_id = fields.Many2one(
        related="planning_slot_id.resource_id",
        string="Chambre",
    )
    product_id = fields.Many2one(
        related="planning_slot_id.sale_line_id.product_id",
        string="Produit",
    )
    selected = fields.Boolean(
        string="Sélectionner",
        default=True,
    )