from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    x_include_pos_extras = fields.Boolean(
        string="Inclure les extras et services dus",
        help="Si coché, les consommations POS transférées au folio et encore dues, "
             "ainsi que les services ajoutés manuellement, seront ajoutés comme lignes "
             "de la facture (comptes de vente dédiés 707200/707300), en plus des lignes "
             "de chambres. Uniquement disponible pour une facture normale (pas un acompte).",
    )
    x_has_due_pos_extras = fields.Boolean(
        string="A des extras ou services dus",
        compute="_compute_x_has_due_pos_extras",
        help="Technique : détermine si la case 'Inclure les extras et services dus' doit être visible.",
    )

    @api.depends("sale_order_ids")
    def _compute_x_has_due_pos_extras(self):
        for wizard in self:
            charges = (
                wizard.sale_order_ids.x_folio_charge_normal_ids
                + wizard.sale_order_ids.x_folio_charge_service_ids
            )
            wizard.x_has_due_pos_extras = bool(
                charges.filtered(lambda c: c.payment_status == "due")
            )

    def create_invoices(self):
        self._check_amount_is_positive()
        invoices = self._create_invoices(self.sale_order_ids)
        if self.advance_payment_method == "delivered" and self.x_include_pos_extras:
            self._add_pos_extras_lines(invoices)
        self._reconcile_down_payment_lines(invoices)
        return self.sale_order_ids.action_view_invoice(invoices=invoices)

    def _reconcile_down_payment_lines(self, invoices):
        """Rapproche automatiquement, sur chaque facture finale, la ligne de
        déduction d'acompte (419100) avec la ligne correspondante sur la
        facture d'acompte d'origine (via le mécanisme natif
        _get_downpayment_lines). Sans ça, cet acompte reste indéfiniment en
        résiduel ouvert des deux côtés — comportement natif Odoo standard
        qui laisse ce rapprochement au comptable, automatisé ici."""
        for invoice in invoices:
            downpayment_lines = invoice.line_ids.filtered(
                lambda l: l.sale_line_ids.filtered("is_downpayment") and not l.reconciled
            )
            for line in downpayment_lines:
                origin_lines = line._get_downpayment_lines().filtered(
                    lambda l: not l.reconciled
                )
                if origin_lines:
                    (line + origin_lines).reconcile()

    def _add_pos_extras_lines(self, invoices):
        """Ajoute les extras et services dus du folio comme lignes supplémentaires
        sur la facture générée, chacun sur son compte de vente dédié (707200 pour
        les extras, 707300 pour les services — distinct de 411200/411300 réservés
        au suivi de créance interne action_settle/action_refund_settled, un compte
        'à recevoir' ne pouvant pas servir de ligne produit sur une facture,
        contrainte native Odoo), et marque les charges incluses via x_invoice_id
        pour éviter qu'elles ne soient proposées deux fois.

        Ces charges ont DÉJÀ généré du revenu (707200/707300 pour un ajout manuel,
        707000 ou équivalent pour une vente POS classique) au moment de leur
        création. Les ajouter en ligne de facture créerait donc un double-comptage
        du revenu. Pour corriger : une écriture manuelle complémentaire (débit
        707200 ou 707300 / crédit 411200 ou 411300 selon le type) est postée pour
        chaque charge, ce qui neutralise le double-comptage ET éteint enfin la
        dette d'origine — rapprochée immédiatement si l'écriture débit d'origine
        (session POS ou ajout manuel) existe déjà, sinon laissée pour le night
        audit."""
        self.ensure_one()
        due_charges = (
            self.sale_order_ids.x_folio_charge_normal_ids
            + self.sale_order_ids.x_folio_charge_service_ids
        ).filtered(lambda c: c.payment_status == "due")
        if not due_charges:
            return

        company_id = self.company_id.id or self.env.company.id

        extras_income_account = self.env["account.account"].search([
            ("code", "=", "707200"),
            ("company_ids", "in", company_id),
        ], limit=1)
        if not extras_income_account:
            raise UserError("Le compte 707200 (Ventes extras chambre) est introuvable.")

        room_charge_account = self.env["account.account"].search([
            ("code", "=", "411200"),
            ("company_ids", "in", company_id),
        ], limit=1)
        if not room_charge_account:
            raise UserError("Le compte 411200 (Créances Transferts Chambre) est introuvable.")

        services_income_account = self.env["account.account"].search([
            ("code", "=", "707300"),
            ("company_ids", "in", company_id),
        ], limit=1)
        if not services_income_account:
            raise UserError("Le compte 707300 (Ventes services chambre) est introuvable.")

        service_charge_account = self.env["account.account"].search([
            ("code", "=", "411300"),
            ("company_ids", "in", company_id),
        ], limit=1)
        if not service_charge_account:
            raise UserError("Le compte 411300 (Créances Service Chambre) est introuvable.")

        general_journal = self.env["account.journal"].search([
            ("type", "=", "general"),
            ("company_id", "=", company_id),
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
                        "account_id": (
                            services_income_account.id if charge.is_service else extras_income_account.id
                        ),
                    })
                    for charge in charges_for_invoice
                ],
            })
            charges_for_invoice.write({"x_invoice_id": invoice.id})

            for charge in charges_for_invoice:
                income_account = services_income_account if charge.is_service else extras_income_account
                receivable_account = service_charge_account if charge.is_service else room_charge_account
                partner = charge.partner_id or charge.sale_order_id.partner_id
                offset_move = self.env["account.move"].create({
                    "journal_id": general_journal.id,
                    "date": fields.Date.context_today(self),
                    "ref": (
                        f"Correction double-comptage "
                        f"{'service' if charge.is_service else 'extra'} facturé — "
                        f"{charge.name} ({invoice.name})"
                    ),
                    "line_ids": [
                        Command.create({
                            "account_id": income_account.id,
                            "partner_id": partner.id,
                            "name": charge.name,
                            "debit": charge.amount_net,
                            "credit": 0.0,
                        }),
                        Command.create({
                            "account_id": receivable_account.id,
                            "partner_id": partner.id,
                            "name": charge.name,
                            "debit": 0.0,
                            "credit": charge.amount_net,
                        }),
                    ],
                })
                offset_move.action_post()
                charge.write({"x_invoice_offset_move_id": offset_move.id})

                new_credit_line = offset_move.line_ids.filtered(
                    lambda l: l.account_id == receivable_account
                )
                session = (
                    charge.pos_order_id.session_id
                    or charge.original_charge_id.pos_order_id.session_id
                )
                if session and session.move_id:
                    matching_debit = session.move_id.line_ids.filtered(
                        lambda l: l.account_id == receivable_account
                        and l.partner_id == partner
                        and not l.reconciled
                    )
                    if matching_debit:
                        (matching_debit + new_credit_line).reconcile()
                elif charge.x_manual_income_move_id:
                    matching_debit = charge.x_manual_income_move_id.line_ids.filtered(
                        lambda l: l.account_id == receivable_account
                        and l.partner_id == partner
                        and not l.reconciled
                    )
                    if matching_debit:
                        (matching_debit + new_credit_line).reconcile()