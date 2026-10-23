from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelPayerInvoiceWizard(models.TransientModel):
    """« Facturer au client » : une facture SANS la chambre, au nom d'un
    payeur, avec seulement ses consommations (23/10/2026).

    Sert aux clients d'un groupe d'agence (chacun paie ses extras), et à
    facturer des consommations plus tard, une fois la chambre facturée.
    Lignes : pos.hotel.folio.charge._x_invoice_line_commands (partagé).
    Comptabilité : à la confirmation de la facture (account.move._post),
    comme pour toute facture d'hôtel.
    """
    _name = "pos.hotel.payer.invoice.wizard"
    _description = "Facturer les consommations d'un client"

    sale_order_id = fields.Many2one("sale.order", string="Réservation", required=True, readonly=True)
    currency_id = fields.Many2one(related="sale_order_id.currency_id")
    candidate_partner_ids = fields.Many2many("res.partner", compute="_compute_candidates")
    partner_id = fields.Many2one(
        "res.partner",
        string="Client à facturer",
        required=True,
        domain="[('id', 'in', candidate_partner_ids)]",
    )
    include_extras = fields.Boolean(string="Inclure les extras dus", default=True)
    include_services = fields.Boolean(string="Inclure les services dus", default=True)
    include_prepaid = fields.Boolean(
        string="Inclure les consommations déjà réglées",
        help="Facture complète : ses consommations déjà réglées figurent aussi, "
             "avec le paiement déduit (« Réglé pendant le séjour »).",
    )
    extras_amount = fields.Monetary(string="Extras dus", compute="_compute_amounts")
    services_amount = fields.Monetary(string="Services dus", compute="_compute_amounts")
    prepaid_amount = fields.Monetary(string="Déjà réglé", compute="_compute_amounts")
    invoice_layout = fields.Selection(
        [
            ("detailed", "Détaillée (une ligne par consommation)"),
            ("summary", "Récapitulative (une ligne par ticket)"),
        ],
        string="Présentation",
        default="detailed",
        required=True,
    )

    def _x_all_charges(self):
        order = self.sale_order_id
        return order.x_folio_charge_normal_ids + order.x_folio_charge_service_ids

    @api.depends("sale_order_id")
    def _compute_candidates(self):
        for wizard in self:
            payers = self.env["res.partner"]
            for charge in wizard._x_all_charges().filtered(
                lambda c: c._x_is_invoiceable() or c._x_is_invoiceable_prepaid()
            ):
                payers |= charge._x_payer()
            wizard.candidate_partner_ids = payers

    def _x_partner_charges(self):
        return self._x_all_charges().filtered(lambda c: c._x_payer() == self.partner_id)

    @api.depends("sale_order_id", "partner_id")
    def _compute_amounts(self):
        for wizard in self:
            charges = wizard._x_partner_charges() if wizard.partner_id else self.env["pos.hotel.folio.charge"]
            wizard.extras_amount = sum(charges.filtered(
                lambda c: not c.is_service and c._x_is_invoiceable()).mapped("amount_net"))
            wizard.services_amount = sum(charges.filtered(
                lambda c: c.is_service and c._x_is_invoiceable()).mapped("amount_net"))
            wizard.prepaid_amount = sum(charges.filtered(
                lambda c: c._x_is_invoiceable_prepaid()).mapped("amount_net"))

    def _x_selected_charges(self):
        self.ensure_one()
        charges = self._x_partner_charges()
        selected = self.env["pos.hotel.folio.charge"]
        if self.include_extras:
            selected |= charges.filtered(lambda c: not c.is_service and c._x_is_invoiceable())
        if self.include_services:
            selected |= charges.filtered(lambda c: c.is_service and c._x_is_invoiceable())
        if self.include_prepaid:
            selected |= charges.filtered(lambda c: c._x_is_invoiceable_prepaid())
        return selected

    def action_confirm(self):
        self.ensure_one()
        charges = self._x_selected_charges()
        if not charges:
            raise UserError("Aucune consommation à facturer pour ce client avec ces choix.")
        order = self.sale_order_id
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner_id.address_get(["invoice"])["invoice"],
            "currency_id": order.currency_id.id,
            "invoice_origin": order.name,
            "invoice_line_ids": charges._x_invoice_line_commands(self.invoice_layout),
        })
        charges.write({"x_invoice_id": invoice.id})
        order.message_post(
            body=f"Facture en brouillon créée pour {self.partner_id.name} : "
                 f"{len(charges)} consommation(s)."
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }
