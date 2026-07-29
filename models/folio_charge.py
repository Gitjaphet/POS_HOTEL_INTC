from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelFolioCharge(models.Model):
    _name = "pos.hotel.folio.charge"
    _description = "Consommation POS transférée sur un folio de séjour"
    _order = "date desc"

    name = fields.Char(
        string="Description",
        required=True,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Folio",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Occupant",
        help="Client en chambre ayant consommé.",
    )
    pos_order_id = fields.Many2one(
        "pos.order",
        string="Commande POS",
        ondelete="restrict",
        help="Commande POS d'origine, pour traçabilité.",
    )
    pos_order_line_id = fields.Many2one(
        "pos.order.line",
        string="Ligne de commande POS",
        ondelete="restrict",
        index=True,
        help="Ligne POS d'origine ayant généré cette ligne folio, pour retrouver ce qui doit être compensé en cas de remboursement.",
    )
    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne du folio (chambre)",
        ondelete="restrict",
        index=True,
        help="Ligne de la réservation (chambre précise) à laquelle cette charge doit être imputée, pour une facturation séparée par chambre.",
    )
    x_room_resource_id = fields.Many2one(
        "resource.resource",
        string="Chambre (ressource précise)",
        ondelete="restrict",
        index=True,
        help="Ressource physique (chambre) précise ayant consommé cette charge, "
             "distincte de sale_order_line_id qui peut regrouper plusieurs chambres.",
    )
    occupant_display = fields.Char(
        string="Occupant",
        compute="_compute_occupant_display",
        store=True,
        help="Nom du client suivi de la chambre précise ('Client - Chambre 401').",
    )
    amount = fields.Monetary(
        string="Montant",
        required=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        store=True,
    )
    date = fields.Datetime(
        string="Date",
        required=True,
        default=fields.Datetime.now,
    )
    payment_status = fields.Selection(
        [
            ("paid_pos", "Payé au POS"),
            ("due", "Dû"),
            ("settled", "Réglé"),
        ],
        string="Statut",
        required=True,
        default="due",
    )
    company_id = fields.Many2one(
        related="sale_order_id.company_id",
        store=True,
    )
    pos_config_id = fields.Many2one(
        "pos.config",
        related="pos_order_id.session_id.config_id",
        string="Point de Vente",
        store=True,
        readonly=True,
    )
    is_refund = fields.Boolean(
        string="Est un remboursement",
        default=False,
        help="Coché automatiquement pour les lignes créées en compensation d'un remboursement POS.",
    )
    original_charge_id = fields.Many2one(
        "pos.hotel.folio.charge",
        string="Charge d'origine",
        ondelete="restrict",
        index=True,
        help="Si cette ligne est un remboursement, référence la ligne folio qu'elle compense.",
    )
    settlement_payment_id = fields.Many2one(
        "account.payment",
        string="Paiement de règlement",
        ondelete="restrict",
        index=True,
        help="Paiement ayant soldé cette charge due (bascule payment_status vers 'settled').",
    )
    refund_charge_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "original_charge_id",
        string="Remboursements liés",
    )
    amount_refunded = fields.Monetary(
        string="Montant remboursé",
        compute="_compute_amount_refunded",
        store=True,
        help="Somme des remboursements liés à cette ligne (valeur positive).",
    )
    amount_net = fields.Monetary(
        string="Montant net",
        compute="_compute_amount_refunded",
        store=True,
        help="Montant restant après déduction des remboursements liés.",
    )
    refund_status = fields.Selection(
        [
            ("none", "Aucun"),
            ("partial", "Partiel"),
            ("full", "Intégral"),
        ],
        string="Statut remboursement",
        compute="_compute_amount_refunded",
        store=True,
    )

    @api.depends("amount", "refund_charge_ids.amount")
    def _compute_amount_refunded(self):
        for charge in self:
            refunded = -sum(charge.refund_charge_ids.mapped("amount"))
            charge.amount_refunded = refunded
            charge.amount_net = charge.amount - refunded
            if charge.currency_id.is_zero(refunded):
                charge.refund_status = "none"
            elif charge.currency_id.is_zero(charge.amount_net):
                charge.refund_status = "full"
            else:
                charge.refund_status = "partial"

    @api.depends("partner_id", "x_room_resource_id")
    def _compute_occupant_display(self):
        for charge in self:
            if charge.partner_id and charge.x_room_resource_id:
                charge.occupant_display = f"{charge.partner_id.name} - Chambre {charge.x_room_resource_id.name}"
            else:
                charge.occupant_display = charge.partner_id.name or ""

    @api.model
    def _create_from_pos_order_line(self, pos_order, sale_order, line, payment_status, amount=None, sale_order_line=None, room_resource=None):
        return self.create({
            "name": line.full_product_name or line.product_id.display_name,
            "sale_order_id": sale_order.id,
            "sale_order_line_id": sale_order_line.id if sale_order_line else False,
            "x_room_resource_id": room_resource.id if room_resource else False,
            "partner_id": pos_order.partner_id.id,
            "pos_order_id": pos_order.id,
            "pos_order_line_id": line.id,
            "amount": amount if amount is not None else line.price_subtotal_incl,
            "payment_status": payment_status,
        })
    
    @api.model
    def _create_refund_from_charge(self, original_charge, pos_order, refund_line, ratio):
        return self.create({
            "name": f"Remboursement — {original_charge.name}",
            "sale_order_id": original_charge.sale_order_id.id,
            "sale_order_line_id": original_charge.sale_order_line_id.id,
            "x_room_resource_id": original_charge.x_room_resource_id.id,
            "partner_id": original_charge.partner_id.id,
            "pos_order_id": pos_order.id,
            "pos_order_line_id": refund_line.id,
            "amount": -original_charge.amount * ratio,
            "payment_status": original_charge.payment_status,
            "is_refund": True,
            "original_charge_id": original_charge.id,
        })

    def _split_due(self, amount):
        """Scinde une charge 'due' en deux : une partie à régler immédiatement
        (montant `amount`, retournée), le reste restant 'due' sur la charge d'origine."""
        self.ensure_one()
        remainder = self.amount_net - amount
        settle_part = self.copy({
            "amount": amount,
            "payment_status": "due",
        })
        self.write({"amount": remainder})
        return settle_part

    @api.model
    def _settle_amount_for_order(self, sale_order, amount, payment_method_line_id):
        """Sélectionne les charges 'due' les plus anciennes du folio jusqu'à couvrir
        `amount`, scindant la dernière si besoin, puis les règle en un seul paiement."""
        due_charges = self.search([
            ("sale_order_id", "=", sale_order.id),
            ("payment_status", "=", "due"),
        ], order="date asc")

        total_due = sum(due_charges.mapped("amount_net"))
        currency = sale_order.currency_id
        if currency.compare_amounts(amount, total_due) > 0:
            raise UserError(
                f"Le montant saisi ({amount}) dépasse le total dû ({total_due}). "
                "Corrigez le montant avant de régler."
            )

        remaining = amount
        to_settle = self.browse()
        for charge in due_charges:
            if charge.currency_id.is_zero(remaining):
                break
            charge_amount = charge.amount_net
            if charge.currency_id.compare_amounts(remaining, charge_amount) >= 0:
                to_settle += charge
                remaining -= charge_amount
            else:
                to_settle += charge._split_due(remaining)
                remaining = 0.0

        if to_settle:
            to_settle.action_settle(payment_method_line_id)
        return to_settle

    def action_settle(self, payment_method_line_id):
            """Règle les charges 'due' sélectionnées en un seul paiement groupé,
            posté et réconcilié avec les écritures POS d'origine (compte 411200,
            nominatives depuis l'activation de split_transactions sur le moyen
            de paiement Transfert Chambre — voir migration 19.0.1.0.6).
            Toutes les charges doivent appartenir au même folio et au même statut 'due'.
            """
            if not self:
                return
            if any(charge.payment_status != "due" for charge in self):
                raise UserError("Seules les charges au statut 'Dû' peuvent être réglées.")
            if len(self.sale_order_id) > 1:
                raise UserError("Impossible de régler des charges appartenant à des folios différents en une seule fois.")

            payment_method_line = self.env["account.payment.method.line"].browse(payment_method_line_id)
            sale_order = self.sale_order_id
            partner = self.partner_id or sale_order.partner_id
            currency = sale_order.currency_id
            company = sale_order.company_id
            total_amount = sum(self.mapped("amount_net"))

            room_charge_account = self.env["account.account"].search([
                ("code", "=", "411200"),
                ("company_ids", "in", company.id),
            ], limit=1)
            if not room_charge_account:
                raise UserError("Le compte 411200 (Créances Transferts Chambre) est introuvable.")

            payment = self.env["account.payment"].create({
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": partner.id,
                "amount": total_amount,
                "journal_id": payment_method_line.journal_id.id,
                "payment_method_line_id": payment_method_line.id,
                "currency_id": currency.id,
                "memo": f"Règlement extras — {sale_order.name}",
                "destination_account_id": room_charge_account.id,
            })
            payment.action_post()

            # Réconciliation : les créances Transfert Chambre nominatives vivent
            # dans l'écriture comptable de CHAQUE SESSION POS (self.move_id sur
            # pos.session), pas dans un account_move individuel par paiement.
            # On les retrouve par compte (411200) + partenaire, seul repère fiable
            # depuis que split_transactions=True rend ces lignes nominatives.
            pos_sessions = self.pos_order_line_id.order_id.session_id

            lines_to_reconcile = payment.move_id.line_ids.filtered(
                lambda l: l.account_id == room_charge_account and not l.reconciled
            )
            if pos_sessions:
                lines_to_reconcile += pos_sessions.mapped("move_id.line_ids").filtered(
                    lambda l: l.account_id == room_charge_account
                    and l.partner_id == partner
                    and not l.reconciled
                )
            if len(lines_to_reconcile.mapped("account_id")) == 1 and len(lines_to_reconcile) > 1:
                lines_to_reconcile.reconcile()

            self.write({
                "payment_status": "settled",
                "settlement_payment_id": payment.id,
            })
            return payment