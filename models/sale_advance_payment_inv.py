from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    x_include_pos_extras = fields.Boolean(
        string="Inclure les extras dus",
        help="Si coché, les consommations POS transférées au folio et encore dues "
             "seront ajoutées comme lignes de la facture (compte 707200 dédié), "
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
        facture générée, sur le compte 707200 (compte de vente dédié, distinct
        du 411200 réservé au suivi de créance interne action_settle/
        action_refund_settled — un compte 'à recevoir' ne peut pas servir de
        ligne produit sur une facture, contrainte native Odoo), et marque les
        charges incluses via x_invoice_id pour éviter qu'elles ne soient
        proposées deux fois.

        Ces charges ont DÉJÀ généré du revenu sur 707000 (ou équivalent) au
        moment de la vente POS et de la clôture de session (ligne 411200
        débit). Les ajouter en ligne de facture sur 707200 créerait donc un
        double-comptage du revenu. Pour corriger : une écriture manuelle
        complémentaire (débit 707200 / crédit 411200) est postée pour chaque
        charge, ce qui neutralise le double-comptage ET éteint enfin la dette
        d'origine sur 411200 — rapprochée immédiatement si la ligne débit de
        session existe déjà (session fermée), sinon laissée pour le night
        audit dès que la session sera fermée."""
        self.ensure_one()
        due_charges = self.sale_order_ids.x_folio_charge_normal_ids.filtered(
            lambda c: c.payment_status == "due"
        )
        if not due_charges:
            return

        extras_income_account = self.env["account.account"].search([
            ("code", "=", "707200"),
            ("company_ids", "in", self.company_id.id or self.env.company.id),
        ], limit=1)
        if not extras_income_account:
            raise UserError("Le compte 707200 (Ventes extras chambre) est introuvable.")

        room_charge_account = self.env["account.account"].search([
            ("code", "=", "411200"),
            ("company_ids", "in", self.company_id.id or self.env.company.id),
        ], limit=1)
        if not room_charge_account:
            raise UserError("Le compte 411200 (Créances Transferts Chambre) est introuvable.")

        general_journal = self.env["account.journal"].search([
            ("type", "=", "general"),
            ("company_id", "=", self.company_id.id or self.env.company.id),
        ], limit=1)
        if not general_journal:
            raise UserError("Aucun journal 'Opérations diverses' trouvé.")

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
                        "account_id": extras_income_account.id,
                    })
                    for charge in charges_for_invoice
                ],
            })
            charges_for_invoice.write({"x_invoice_id": invoice.id})

            for charge in charges_for_invoice:
                partner = charge.partner_id or charge.sale_order_id.partner_id
                offset_move = self.env["account.move"].create({
                    "journal_id": general_journal.id,
                    "date": fields.Date.context_today(self),
                    "ref": f"Correction double-comptage extra facturé — {charge.name} ({invoice.name})",
                    "line_ids": [
                        Command.create({
                            "account_id": extras_income_account.id,
                            "partner_id": partner.id,
                            "name": charge.name,
                            "debit": charge.amount_net,
                            "credit": 0.0,
                        }),
                        Command.create({
                            "account_id": room_charge_account.id,
                            "partner_id": partner.id,
                            "name": charge.name,
                            "debit": 0.0,
                            "credit": charge.amount_net,
                        }),
                    ],
                })
                offset_move.action_post()

                new_credit_line = offset_move.line_ids.filtered(
                    lambda l: l.account_id == room_charge_account
                )
                session = (
                    charge.pos_order_id.session_id
                    or charge.original_charge_id.pos_order_id.session_id
                )
                if session and session.move_id:
                    matching_debit = session.move_id.line_ids.filtered(
                        lambda l: l.account_id == room_charge_account
                        and l.partner_id == partner
                        and not l.reconciled
                    )
                    if matching_debit:
                        (matching_debit + new_credit_line).reconcile()