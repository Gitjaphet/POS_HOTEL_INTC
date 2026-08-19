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
    reason = fields.Text(
        string="Motif (si départ avec dette non réglée)",
    )

    def action_confirm(self):
        self.ensure_one()
        selected = self.line_ids.filtered("selected")
        if not selected:
            raise UserError("Sélectionnez au moins une chambre.")
        now = fields.Datetime.now()
        for line in selected:
            slot = line.planning_slot_id
            if self.status == "checkin":
                if slot.start_datetime and now < slot.start_datetime:
                    slot.sale_line_id._adjust_room_stay_date(slot, 'start', now)
                slot.write({
                    "x_stay_status": "checked_in",
                    "x_checked_in_at": now,
                })
                slot.sale_line_id.update({"qty_delivered": slot.sale_line_id.qty_delivered + 1})
            else:
                if line.x_due_amount and not line.cancel_due_debt:
                    raise UserError(
                        f"La chambre {slot.resource_id.name} a encore {line.x_due_amount} "
                        f"{line.currency_id.symbol} d'extras non réglés. Cochez "
                        "'Annuler la dette due sur cette chambre' (avec motif) pour "
                        "continuer, ou réglez d'abord ces extras."
                    )
                if line.x_due_amount and line.cancel_due_debt:
                    if not self.reason:
                        raise UserError(
                            "Un motif est requis pour annuler la dette au départ."
                        )
                    due_charges = self.env["pos.hotel.folio.charge"].search([
                        ("sale_order_line_id", "=", slot.sale_line_id.id),
                        ("x_room_resource_id", "=", slot.resource_id.id),
                        ("payment_status", "=", "due"),
                        ("x_invoice_id", "=", False),
                    ])
                    due_charges._transition_to_cancelled(reason=self.reason)
                    self.order_id.message_post(
                        body=f"Départ chambre {slot.resource_id.name} avec dette annulée "
                             f"({line.x_due_amount} {line.currency_id.symbol}). "
                             f"Motif : {self.reason}"
                    )
                if slot.end_datetime and now < slot.end_datetime:
                    slot.sale_line_id._adjust_room_stay_date(slot, 'end', now)
                slot.write({
                    "x_stay_status": "checked_out",
                    "x_checked_out_at": now,
                })
                slot.sale_line_id.update({"qty_returned": slot.sale_line_id.qty_returned + 1})
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
    x_due_amount = fields.Monetary(
        string="Montant dû sur cette chambre",
        compute="_compute_x_due_amount",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        related="wizard_id.order_id.currency_id",
    )
    cancel_due_debt = fields.Boolean(
        string="Annuler la dette due sur cette chambre",
    )

    @api.depends("planning_slot_id", "wizard_id.status")
    def _compute_x_due_amount(self):
        for line in self:
            if line.wizard_id.status != "checkout":
                line.x_due_amount = 0.0
                continue
            due_charges = self.env["pos.hotel.folio.charge"].search([
                ("sale_order_line_id", "=", line.planning_slot_id.sale_line_id.id),
                ("x_room_resource_id", "=", line.resource_id.id),
                ("payment_status", "=", "due"),
                ("x_invoice_id", "=", False),
            ])
            line.x_due_amount = sum(due_charges.mapped("amount_net"))