from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    x_include_pos_extras = fields.Boolean(
        string="Inclure les extras dus",
        help="Si coché, les consommations (point de vente et extras ajoutés par "
             "l'hôtel) encore dues sont ajoutées à la facture (compte 707200), en "
             "plus des lignes de chambres. Uniquement pour une facture normale.",
    )
    x_include_services = fields.Boolean(
        string="Inclure les services dus",
        help="Si coché, les services encore dus (excursions, navettes...) sont "
             "ajoutés à la facture (compte 707300). Uniquement pour une facture normale.",
    )
    x_due_extras_amount = fields.Monetary(
        string="Extras dus",
        compute="_compute_x_has_due_pos_extras",
        currency_field="x_currency_id",
    )
    x_due_services_amount = fields.Monetary(
        string="Services dus",
        compute="_compute_x_has_due_pos_extras",
        currency_field="x_currency_id",
    )
    x_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_x_has_due_pos_extras",
    )
    x_invoice_layout = fields.Selection(
        [
            ("detailed", "Détaillée (une ligne par consommation)"),
            ("summary", "Récapitulative (une ligne par ticket)"),
        ],
        string="Présentation des extras",
        default="detailed",
        required=True,
        help="Détaillée : chaque consommation, avec sa date et le détail des formules. "
             "Récapitulative : les consommations du point de vente regroupées par "
             "ticket (date, référence, total), pour les longs séjours et les groupes. "
             "La comptabilité est identique dans les deux cas.",
    )
    x_has_due_pos_extras = fields.Boolean(
        string="A des extras ou services dus",
        compute="_compute_x_has_due_pos_extras",
        help="Technique : détermine si la case 'Inclure les extras et services dus' doit être visible.",
    )

    @api.depends("sale_order_ids")
    def _compute_x_has_due_pos_extras(self):
        for wizard in self:
            orders = wizard.sale_order_ids
            extras = orders.x_folio_charge_normal_ids.filtered(lambda c: c._x_is_invoiceable())
            services = orders.x_folio_charge_service_ids.filtered(lambda c: c._x_is_invoiceable())
            wizard.x_currency_id = orders[:1].currency_id or self.env.company.currency_id
            wizard.x_due_extras_amount = sum(extras.mapped("amount_net"))
            wizard.x_due_services_amount = sum(services.mapped("amount_net"))
            wizard.x_has_due_pos_extras = bool(extras or services)

    def create_invoices(self):
        self._check_amount_is_positive()
        invoices = self._create_invoices(self.sale_order_ids)
        if self.advance_payment_method == "delivered" and (
            self.x_include_pos_extras or self.x_include_services
        ):
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

    def _x_local_dt(self, dt, fmt):
        return fields.Datetime.context_timestamp(self, dt).strftime(fmt) if dt else ""

    def _x_charge_label(self, charge):
        """Présentation détaillée : « 22/10 — Nom », puis les articles d'une
        formule sur les lignes suivantes."""
        label = f"{self._x_local_dt(charge.date, '%d/%m')} — {charge.name}"
        if charge.x_combo_detail:
            label += "\n" + "\n".join(f"· {item}" for item in charge.x_combo_detail.splitlines())
        return label

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
        audit.

        Depuis le 23/10/2026, la compensation n'est plus créée ici mais à la
        CONFIRMATION de la facture (account.move._post ->
        folio_charge_offset._x_post_invoice_offset).

        Présentation (x_invoice_layout) : détaillée (une ligne par charge) ou
        récapitulative (charges POS regroupées par ticket). Les écritures de
        compensation restent une par charge dans les deux cas. Les charges
        remboursées intégralement (net 0) ne sont jamais facturées."""
        self.ensure_one()
        due_charges = self.env["pos.hotel.folio.charge"]
        if self.x_include_pos_extras:
            due_charges |= self.sale_order_ids.x_folio_charge_normal_ids
        if self.x_include_services:
            due_charges |= self.sale_order_ids.x_folio_charge_service_ids
        due_charges = due_charges.filtered(lambda c: c._x_is_invoiceable())
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

            extras = charges_for_invoice.filtered(lambda c: not c.is_service)
            services = charges_for_invoice.filtered(lambda c: c.is_service)
            extras_pos = extras.filtered(lambda c: c.pos_order_id)
            extras_manual = extras - extras_pos

            def _charge_line(charge):
                return Command.create({
                    "name": self._x_charge_label(charge),
                    "quantity": 1.0,
                    "price_unit": charge.amount_net,
                    "account_id": (
                        services_income_account.id if charge.is_service else extras_income_account.id
                    ),
                })

            def _ticket_lines(charges):
                """Récapitulative : une ligne par ticket POS, au total de ses
                consommations dues, dans l'ordre chronologique."""
                commands = []
                for order in charges.pos_order_id.sorted("date_order"):
                    order_charges = charges.filtered(lambda c: c.pos_order_id == order)
                    commands.append(Command.create({
                        "name": (
                            f"{self._x_local_dt(order.date_order, '%d/%m %H:%M')} — "
                            f"Ticket {order.pos_reference} ({order.config_id.name})"
                        ),
                        "quantity": 1.0,
                        "price_unit": sum(order_charges.mapped("amount_net")),
                        "account_id": extras_income_account.id,
                    }))
                return commands

            line_commands = []
            if extras:
                line_commands.append(Command.create({"display_type": "line_section", "name": "Extras"}))
                if extras_pos:
                    line_commands.append(Command.create({"display_type": "line_subsection", "name": "Restaurant / Bar"}))
                    if self.x_invoice_layout == "summary":
                        line_commands += _ticket_lines(extras_pos)
                    else:
                        line_commands += [_charge_line(c) for c in extras_pos.sorted("date")]
                if extras_manual:
                    line_commands.append(Command.create({"display_type": "line_subsection", "name": "Ajoutés par l'hôtel"}))
                    line_commands += [_charge_line(c) for c in extras_manual.sorted("date")]
            if services:
                line_commands.append(Command.create({"display_type": "line_section", "name": "Services"}))
                line_commands += [_charge_line(c) for c in services.sorted("date")]

            invoice.write({"invoice_line_ids": line_commands})
            charges_for_invoice.write({"x_invoice_id": invoice.id})
