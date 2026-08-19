from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


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
            ("cancelled", "Annulée (chambre retirée)"),
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
    is_service = fields.Boolean(
        string="Est un service",
        default=False,
        store=True,
        help="Coché automatiquement si le produit d'origine est de type Service (massage, transport, laverie...).",
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
    x_invoice_id = fields.Many2one(
        "account.move",
        string="Facture",
        ondelete="restrict",
        index=True,
        help="Facture ayant inclus cette charge (si incluse dans la facture globale du folio). "
             "Indépendant de payment_status : une charge peut être facturée et toujours 'due' "
             "si le client n'a pas encore réglé la facture. Vide tant que la charge n'a jamais "
             "été incluse dans une facture.",
    )
    x_invoice_is_active = fields.Boolean(
        string="Facture active",
        compute="_compute_invoice_is_active",
        store=True,
        help="True si x_invoice_id pointe vers une facture ni annulée ni extournée. "
            "Permet de distinguer une charge réellement encore facturée d'une charge "
            "dont la facture a été annulée/extournée depuis (redevient 'due' de fait).",
    )
    x_invoice_offset_move_id = fields.Many2one(
        "account.move",
        string="Écriture de compensation",
        ondelete="restrict",
        index=True,
        help="Écriture manuelle (débit 707200/crédit 411200) postée pour "
             "neutraliser le double-comptage de revenu quand cette charge "
             "a été incluse dans une facture. Sert au night audit pour "
             "retrouver le crédit 411200 correspondant à cette charge.",
    )
    x_manual_income_move_id = fields.Many2one(
        "account.move",
        string="Écriture de revenu (ajout manuel)",
        ondelete="restrict",
        index=True,
        help="Écriture comptable (débit créance/crédit revenu) postée automatiquement "
             "quand cette charge a été ajoutée manuellement côté hôtel (hors POS), "
             "pour simuler ce que la clôture de session POS aurait généré. "
             "Vide pour les charges créées depuis une commande POS.",
    )
    x_reversal_move_id = fields.Many2one(
        "account.move",
        string="Écriture d'extourne",
        ondelete="restrict",
        index=True,
        copy=False,
        help="Écriture de compensation (débit revenu / crédit créance) postée "
             "quand cette charge est annulée ou remboursée, pour neutraliser le "
             "revenu constaté à sa création. Indispensable au night audit pour "
             "rattacher le crédit 411200/411300 correspondant.",
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
    @api.depends("x_invoice_id.state", "x_invoice_id.payment_state")
    def _compute_invoice_is_active(self):
        for charge in self:
            charge.x_invoice_is_active = bool(
                charge.x_invoice_id
                and charge.x_invoice_id.state != 'cancel'
                and charge.x_invoice_id.payment_state != 'reversed'
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

    @api.model
    def _create_manual_charge(self, vals, is_service=False):
        """Crée une charge ajoutée manuellement côté hôtel (hors POS) et poste
        immédiatement l'écriture de revenu correspondante (débit créance/crédit
        revenu), puisqu'aucune commande POS/session ne le fera pour elle."""
        charge = self.create({**vals, "is_service": is_service})
        charge._post_manual_income_entry()
        return charge

    def _post_manual_income_entry(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        code_receivable = "411300" if self.is_service else "411200"
        code_income = "707300" if self.is_service else "707200"

        receivable_account = self.env["account.account"].search([
            ("code", "=", code_receivable),
            ("company_ids", "in", company.id),
        ], limit=1)
        if not receivable_account:
            raise UserError(f"Le compte {code_receivable} est introuvable.")

        income_account = self.env["account.account"].search([
            ("code", "=", code_income),
            ("company_ids", "in", company.id),
        ], limit=1)
        if not income_account:
            raise UserError(f"Le compte {code_income} est introuvable.")

        general_journal = self.env["account.journal"].search([
            ("type", "=", "general"),
            ("company_id", "=", company.id),
        ], limit=1)
        if not general_journal:
            raise UserError("Aucun journal 'Opérations diverses' trouvé.")

        partner = self.partner_id or self.sale_order_id.partner_id
        move = self.env["account.move"].create({
            "journal_id": general_journal.id,
            "date": fields.Date.context_today(self),
            "ref": f"Ajout manuel — {self.name} ({self.sale_order_id.name})",
            "line_ids": [
                Command.create({
                    "account_id": receivable_account.id,
                    "partner_id": partner.id,
                    "name": self.name,
                    "debit": self.amount,
                    "credit": 0.0,
                }),
                Command.create({
                    "account_id": income_account.id,
                    "partner_id": partner.id,
                    "name": self.name,
                    "debit": 0.0,
                    "credit": self.amount,
                }),
            ],
        })
        move.action_post()
        self.write({"x_manual_income_move_id": move.id})
        return move


    def _get_receivable_account(self):
        """Compte de créance dédié à cette charge (411200 extras / 411300 services).

        Point d'entrée unique : à terme, c'est ici qu'un champ de configuration
        remplacera la recherche par code, sans toucher aux appelants.
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        code = "411300" if self.is_service else "411200"
        account = self.env["account.account"].search([
            ("code", "=", code),
            ("company_ids", "in", company.id),
        ], limit=1)
        if not account:
            raise UserError(f"Le compte {code} est introuvable.")
        return account

    def _get_reversal_accounts(self):
        """Détermine le couple (compte de revenu, compte de créance) à extourner.

        Principe : on extourne le compte RÉELLEMENT crédité pour cette charge,
        jamais un compte supposé.
          1. Charge manuelle  -> relecture directe de l'écriture de revenu d'origine.
          2. Charge POS       -> compte de revenu du produit (souvent 707000),
                                 remappé par la position fiscale le cas échéant.
          3. Repli            -> comptes dédiés 707200/707300, pour les charges
                                 anciennes qui n'ont ni l'un ni l'autre.
        """
        self.ensure_one()
        if self.is_refund and self.original_charge_id:
            # Une charge de remboursement n'a pas d'origine comptable propre :
            # les comptes à extourner sont ceux de la charge qu'elle compense.
            return self.original_charge_id._get_reversal_accounts()

        company = self.company_id or self.env.company
        income_account = False
        receivable_account = False

        if self.x_manual_income_move_id:
            for line in self.x_manual_income_move_id.line_ids:
                if line.credit and not income_account:
                    income_account = line.account_id
                elif line.debit and not receivable_account:
                    receivable_account = line.account_id

        if not income_account and self.pos_order_line_id.product_id:
            product = self.pos_order_line_id.product_id
            income_account = product.product_tmpl_id._get_product_accounts().get("income")
            fiscal_position = self.pos_order_id.fiscal_position_id
            if fiscal_position and income_account:
                income_account = fiscal_position.map_account(income_account)

        if not income_account:
            pm_model = self.env["pos.payment.method"]
            income_account = (
                pm_model._ensure_service_income_account(company)
                if self.is_service
                else pm_model._ensure_extras_income_account(company)
            )

        if not receivable_account:
            receivable_account = self._get_receivable_account()

        return income_account, receivable_account

    def _post_reversal_entry(self, reason=None, amount=None):
        """Poste l'écriture neutralisant le revenu constaté pour cette charge.

        Miroir exact de _post_manual_income_entry : débit revenu / crédit créance.
        On ne touche JAMAIS à l'écriture d'origine — souvent une écriture de session
        POS agrégée, parfois sur une période close. On poste une écriture neuve
        datée du jour, exactement comme le fait déjà x_invoice_offset_move_id.
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        amount = abs(self.amount_net if amount is None else amount)
        if self.currency_id.is_zero(amount):
            return False

        income_account, receivable_account = self._get_reversal_accounts()

        journal = self.env["account.journal"].search([
            ("type", "=", "general"),
            ("company_id", "=", company.id),
        ], limit=1)
        if not journal:
            raise UserError("Aucun journal 'Opérations diverses' trouvé.")

        partner = self.partner_id or self.sale_order_id.partner_id
        label = self.name if self.is_refund else f"{reason or 'Extourne'} — {self.name}"
        move = self.env["account.move"].create({
            "journal_id": journal.id,
            "date": fields.Date.context_today(self),
            "ref": f"{label} ({self.sale_order_id.name})",
            "line_ids": [
                Command.create({
                    "account_id": income_account.id,
                    "partner_id": partner.id,
                    "name": label,
                    "debit": amount,
                    "credit": 0.0,
                }),
                Command.create({
                    "account_id": receivable_account.id,
                    "partner_id": partner.id,
                    "name": label,
                    "debit": 0.0,
                    "credit": amount,
                }),
            ],
        })
        move.action_post()
        self.write({"x_reversal_move_id": move.id})
        return move

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
    def _settle_amount_for_order(self, sale_order, amount, payment_method_line_id, is_service=False):
        """Sélectionne les charges 'due' les plus anciennes du folio (extras ou
        services selon is_service) jusqu'à couvrir `amount`, scindant la dernière
        si besoin, puis les règle en un seul paiement."""
        due_charges = self.search([
            ("sale_order_id", "=", sale_order.id),
            ("payment_status", "=", "due"),
            ("x_invoice_is_active", "=", False),
            ("is_service", "=", is_service),
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

    def action_open_cancel_wizard(self):
        self.ensure_one()
        if self.payment_status != 'due':
            raise UserError(
                "Seul un extra encore dû peut être annulé ainsi."
            )
        if self.x_invoice_is_active:
            raise UserError(
                f"Cette charge est incluse dans la facture {self.x_invoice_id.name or 'brouillon'}, "
                "qui est toujours active. Annulez ou extournez cette facture "
                "avant de pouvoir annuler la charge."
            )
        return {
            'type': 'ir.actions.act_window',
            'name': "Annuler cet extra",
            'res_model': 'pos.hotel.charge.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_charge_id': self.id},
        }

    def action_open_refund_wizard(self):
        self.ensure_one()
        if self.payment_status != 'settled':
            raise UserError(
                "Seul un extra au statut 'Réglé' peut être remboursé ainsi."
            )
        return {
            'type': 'ir.actions.act_window',
            'name': "Rembourser cet extra",
            'res_model': 'pos.hotel.charge.refund.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_charge_id': self.id},
        }

    def action_settle(self, payment_method_line_id):
            """Règle les charges 'due' sélectionnées en un seul paiement groupé,
            posté et réconcilié avec les écritures POS d'origine (compte 411200
            pour les extras, 411300 pour les services, nominatives depuis
            l'activation de split_transactions sur le moyen de paiement Transfert
            Chambre — voir migration 19.0.1.0.6). Toutes les charges doivent
            appartenir au même folio, au même statut 'due', et au même type
            (extra ou service — comptes de destination différents).
            """
            if not self:
                return
            if any(charge.payment_status != "due" for charge in self):
                raise UserError("Seules les charges au statut 'Dû' peuvent être réglées.")
            if len(self.sale_order_id) > 1:
                raise UserError("Impossible de régler des charges appartenant à des folios différents en une seule fois.")
            if len(set(self.mapped("is_service"))) > 1:
                raise UserError("Impossible de régler des extras et des services dans un même paiement.")

            payment_method_line = self.env["account.payment.method.line"].browse(payment_method_line_id)
            sale_order = self.sale_order_id
            partner = self.partner_id or sale_order.partner_id
            currency = sale_order.currency_id
            company = sale_order.company_id
            total_amount = sum(self.mapped("amount_net"))
            is_service = self[0].is_service
            account_code = "411300" if is_service else "411200"
            account_label = "Créances Service Chambre" if is_service else "Créances Transferts Chambre"

            room_charge_account = self.env["account.account"].search([
                ("code", "=", account_code),
                ("company_ids", "in", company.id),
            ], limit=1)
            if not room_charge_account:
                raise UserError(f"Le compte {account_code} ({account_label}) est introuvable.")

            payment = self.env["account.payment"].create({
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": partner.id,
                "amount": total_amount,
                "journal_id": payment_method_line.journal_id.id,
                "payment_method_line_id": payment_method_line.id,
                "currency_id": currency.id,
                "memo": f"Règlement {'services' if is_service else 'extras'} — {sale_order.name}",
                "destination_account_id": room_charge_account.id,
            })
            payment.action_post()

            # Le lettrage (rapprochement 411200/411300 avec la session POS
            # d'origine ou l'écriture manuelle) n'est PAS tenté ici : une
            # session POS reste "opened" tant que le service tourne, son
            # move_id n'existe qu'à la fermeture. Le rapprochement est une
            # opération de clôture, effectuée au night audit — jamais en
            # temps réel.
            self.write({
                "payment_status": "settled",
                "settlement_payment_id": payment.id,
            })
            return payment


    def action_refund_settled(self, payment_method_line_id):
        """Rembourse les charges 'settled' sélectionnées via un paiement sortant
        (account.payment outbound), symétrique à action_settle(). Crée pour
        chaque charge une charge négative liée via original_charge_id — même
        mécanisme que les remboursements POS (refund_status, amount_net calculés
        automatiquement). La charge d'origine reste au statut 'settled' :
        c'est amount_net/refund_status qui reflète qu'elle est soldée.
        """
        if not self:
            return
        if any(charge.payment_status != "settled" for charge in self):
            raise UserError("Seules les charges au statut 'Réglé' peuvent être remboursées ici.")
        if len(self.sale_order_id) > 1:
            raise UserError("Impossible de rembourser des charges appartenant à des folios différents en une seule fois.")
        if len(set(self.mapped("is_service"))) > 1:
            raise UserError("Impossible de rembourser des extras et des services dans un même paiement.")

        payment_method_line = self.env["account.payment.method.line"].browse(payment_method_line_id)
        sale_order = self.sale_order_id
        partner = self.partner_id or sale_order.partner_id
        currency = sale_order.currency_id
        company = sale_order.company_id
        total_amount = sum(self.mapped("amount_net"))
        is_service = self[0].is_service
        account_code = "411300" if is_service else "411200"
        account_label = "Créances Service Chambre" if is_service else "Créances Transferts Chambre"

        room_charge_account = self.env["account.account"].search([
            ("code", "=", account_code),
            ("company_ids", "in", company.id),
        ], limit=1)
        if not room_charge_account:
            raise UserError(f"Le compte {account_code} ({account_label}) est introuvable.")

        payment = self.env["account.payment"].create({
            "payment_type": "outbound",
            "partner_type": "customer",
            "partner_id": partner.id,
            "amount": total_amount,
            "journal_id": payment_method_line.journal_id.id,
            "payment_method_line_id": payment_method_line.id,
            "currency_id": currency.id,
            "memo": f"Remboursement {'services' if is_service else 'extras'} réglés — {sale_order.name}",
            "destination_account_id": room_charge_account.id,
        })
        payment.action_post()

        refund_charges = self.browse()
        for charge in self:
            refund_charges += self.create({
                "name": f"Remboursement — {charge.name}",
                "sale_order_id": charge.sale_order_id.id,
                "sale_order_line_id": charge.sale_order_line_id.id,
                "x_room_resource_id": charge.x_room_resource_id.id,
                "partner_id": charge.partner_id.id,
                "amount": -charge.amount_net,
                "payment_status": "settled",
                "is_refund": True,
                "is_service": charge.is_service,
                "original_charge_id": charge.id,
                "settlement_payment_id": payment.id,
            })

        # Le lettrage sera fait au night audit (rapprochement différé), pas ici.
                # TROU Y — le paiement ci-dessus ne bouge que caisse <-> créance : sans
        # cette compensation, le revenu resterait constaté malgré l'argent rendu.
        for refund_charge in refund_charges:
            refund_charge._post_reversal_entry(reason="Remboursement")

        return payment