from odoo import api, fields, models


class SaleAdvancePaymentInv(models.TransientModel):
    """Assistant « Créer une facture » : les nuits (lignes natives) plus, au
    choix, les consommations de la réservation.

    - Cases : extras dus, services dus, consommations déjà réglées (facture
      complète, paiement déduit).
    - « Consommations de » : les payeurs dont on inclut les consommations.
      Réservation d'agence : l'agence seule par défaut (les clients ont leur
      propre facture, « Facturer au client ») ; sans agence : tout le monde.
    - Lignes : pos.hotel.folio.charge._x_invoice_line_commands (partagé).
    - Comptabilité (compensation, « Réglé pendant le séjour ») : à la
      confirmation de la facture (account.move._post), jamais au brouillon.
    """
    _inherit = "sale.advance.payment.inv"

    x_include_pos_extras = fields.Boolean(
        string="Inclure les extras dus",
        help="Les consommations (point de vente et extras ajoutés par l'hôtel) "
             "encore dues des payeurs choisis (compte 707200).",
    )
    x_include_services = fields.Boolean(
        string="Inclure les services dus",
        help="Les services encore dus des payeurs choisis (compte 707300).",
    )
    x_include_prepaid = fields.Boolean(
        string="Inclure les consommations déjà réglées",
        help="Facture finale complète : les extras et services déjà réglés à la "
             "réception ou payés au point de vente figurent aussi sur la facture, "
             "avec leur paiement déduit en bas (« Réglé pendant le séjour »).",
    )
    x_payer_candidate_ids = fields.Many2many(
        "res.partner",
        compute="_compute_x_payer_candidates",
        string="Payeurs possibles",
    )
    x_payer_count = fields.Integer(compute="_compute_x_payer_candidates")
    x_payer_ids = fields.Many2many(
        "res.partner",
        "sale_adv_inv_hotel_payer_rel",
        "wizard_id",
        "partner_id",
        string="Consommations de",
        compute="_compute_x_payer_ids",
        store=True,
        readonly=False,
        help="Payeurs dont les consommations vont sur cette facture. Les autres "
             "se facturent à part avec « Facturer au client ».",
    )
    x_prepaid_amount = fields.Monetary(
        string="Déjà réglé",
        compute="_compute_x_has_due_pos_extras",
        currency_field="x_currency_id",
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
        string="A des consommations à facturer",
        compute="_compute_x_payer_candidates",
        help="Technique : affiche le bloc des consommations.",
    )

    def _x_all_charges(self):
        orders = self.sale_order_ids
        return orders.x_folio_charge_normal_ids + orders.x_folio_charge_service_ids

    @api.depends("sale_order_ids")
    def _compute_x_payer_candidates(self):
        for wizard in self:
            charges = wizard._x_all_charges().filtered(
                lambda c: c._x_is_invoiceable() or c._x_is_invoiceable_prepaid()
            )
            payers = self.env["res.partner"]
            for charge in charges:
                payers |= charge._x_payer()
            wizard.x_payer_candidate_ids = payers
            wizard.x_payer_count = len(payers)
            wizard.x_has_due_pos_extras = bool(charges)

    @api.depends("sale_order_ids")
    def _compute_x_payer_ids(self):
        for wizard in self:
            payers = wizard.x_payer_candidate_ids
            agencies = wizard.sale_order_ids.x_agency_partner_id
            wizard.x_payer_ids = payers & agencies if agencies else payers

    @api.depends("sale_order_ids", "x_payer_ids")
    def _compute_x_has_due_pos_extras(self):
        for wizard in self:
            charges = wizard._x_all_charges().filtered(
                lambda c: c._x_payer() in wizard.x_payer_ids
            )
            extras = charges.filtered(lambda c: not c.is_service and c._x_is_invoiceable())
            services = charges.filtered(lambda c: c.is_service and c._x_is_invoiceable())
            prepaid = charges.filtered(lambda c: c._x_is_invoiceable_prepaid())
            wizard.x_currency_id = wizard.sale_order_ids[:1].currency_id or self.env.company.currency_id
            wizard.x_due_extras_amount = sum(extras.mapped("amount_net"))
            wizard.x_due_services_amount = sum(services.mapped("amount_net"))
            wizard.x_prepaid_amount = sum(prepaid.mapped("amount_net"))

    def create_invoices(self):
        self._check_amount_is_positive()
        invoices = self._create_invoices(self.sale_order_ids)
        if self.advance_payment_method == "delivered" and (
            self.x_include_pos_extras or self.x_include_services or self.x_include_prepaid
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

    def _x_selected_charges(self):
        self.ensure_one()
        charges = self._x_all_charges().filtered(lambda c: c._x_payer() in self.x_payer_ids)
        selected = self.env["pos.hotel.folio.charge"]
        if self.x_include_pos_extras:
            selected |= charges.filtered(lambda c: not c.is_service and c._x_is_invoiceable())
        if self.x_include_services:
            selected |= charges.filtered(lambda c: c.is_service and c._x_is_invoiceable())
        if self.x_include_prepaid:
            selected |= charges.filtered(lambda c: c._x_is_invoiceable_prepaid())
        return selected

    def _add_pos_extras_lines(self, invoices):
        """Ajoute aux factures les consommations choisies (cases et payeurs),
        et les relie à leur facture (x_invoice_id) pour qu'elles ne soient
        jamais proposées deux fois. Une consommation remboursée intégralement
        n'est jamais facturée."""
        self.ensure_one()
        selected = self._x_selected_charges()
        if not selected:
            return
        for invoice in invoices:
            charges = selected.filtered(
                lambda c: c.sale_order_id == invoice.invoice_line_ids.sale_line_ids.order_id[:1]
            )
            if not charges:
                continue
            invoice.write({"invoice_line_ids": charges._x_invoice_line_commands(self.x_invoice_layout)})
            charges.write({"x_invoice_id": invoice.id})
