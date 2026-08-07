from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    x_include_pos_extras = fields.Boolean(
        string="Inclure les extras dus",
        help="Si coché, les consommations POS transférées au folio et encore dues "
             "seront ajoutées comme lignes de la facture (compte 411200 conservé), "
             "en plus des lignes de chambres. Uniquement disponible pour une facture "
             "normale (pas un acompte).",
    )
    x_has_due_pos_extras = fields.Boolean(
        string="A des extras dus",
        compute="_compute_x_has_due_pos_extras",
        help="Technique : détermine si la case 'Inclure les extras dus' doit être visible.",
    )

    @api.depends("sale_order_ids")
    def _compute_x_has_due_pos_extras(self):
        for wizard in self:
            wizard.x_has_due_pos_extras = bool(
                wizard.sale_order_ids.x_folio_charge_normal_ids.filtered(
                    lambda c: c.payment_status == "due"
                )
            )

    def create_invoices(self):
        self._check_amount_is_positive()
        invoices = self._create_invoices(self.sale_order_ids)
        if self.advance_payment_method == "delivered" and self.x_include_pos_extras:
            self._add_pos_extras_lines(invoices)
        return self.sale_order_ids.action_view_invoice(invoices=invoices)

    def _add_pos_extras_lines(self, invoices):
        """Ajoute les extras POS dus du folio comme lignes supplémentaires sur la
        facture générée, sur le compte 411200 (même compte que action_settle/
        action_refund_settled), et marque les charges incluses via x_invoice_id
        pour éviter qu'elles ne soient proposées deux fois."""
        self.ensure_one()
        due_charges = self.sale_order_ids.x_folio_charge_normal_ids.filtered(
            lambda c: c.payment_status == "due"
        )
        if not due_charges:
            return

        room_charge_account = self.env["account.account"].search([
            ("code", "=", "411200"),
            ("company_ids", "in", self.company_id.id or self.env.company.id),
        ], limit=1)
        if not room_charge_account:
            raise UserError("Le compte 411200 (Créances Transferts Chambre) est introuvable.")

        for invoice in invoices:
            charges_for_invoice = due_charges.filtered(
                lambda c: c.sale_order_id == invoice.invoice_line_ids.sale_line_ids.order_id[:1]
            )
            if not charges_for_invoice:
                continue
            invoice.write({
                "invoice_line_ids": [
                    Command.create({
                        "name": charge.name,
                        "quantity": 1.0,
                        "price_unit": charge.amount_net,
                        "account_id": room_charge_account.id,
                    })
                    for charge in charges_for_invoice
                ],
            })
            charges_for_invoice.write({"x_invoice_id": invoice.id})