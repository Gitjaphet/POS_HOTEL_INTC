import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    is_room_charge = fields.Boolean(
        string="Transfert vers chambre",
        help="Si activé, ce moyen de paiement ouvre la recherche de chambre/séjour "
             "au lieu d'encaisser directement. Le montant est imputé au folio du client.",
    )

    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + ["is_room_charge"]

    # --- Comptes par défaut ------------------------------------------------
    # Utilisés SEULEMENT pour remplir un réglage vide de la société
    # (res.company._x_hotel_account) : trouvent le compte par son numéro
    # par défaut, ou le créent. Le reste du module lit le réglage.

    @api.model
    def _ensure_extras_receivable_account(self, company):
        account = self.env["account.account"].search([
            ("code", "=", "411200"),
            ("company_ids", "in", company.id),
        ], limit=1)
        if not account:
            account = self.env["account.account"].create({
                "code": "411200",
                "name": "Créances Transferts Chambre",
                "account_type": "asset_receivable",
                "company_ids": [(6, 0, [company.id])],
                "reconcile": True,
            })
        return account

    @api.model
    def _ensure_extras_income_account(self, company):
        account = self.env["account.account"].search([
            ("code", "=", "707200"),
            ("company_ids", "in", company.id),
        ], limit=1)
        if not account:
            account = self.env["account.account"].create({
                "code": "707200",
                "name": "Ventes extras chambre",
                "account_type": "income",
                "company_ids": [(6, 0, [company.id])],
            })
        return account

    @api.model
    def _ensure_service_charge_account(self, company):
        account = self.env["account.account"].search([
            ("code", "=", "411300"),
            ("company_ids", "in", company.id),
        ], limit=1)
        if not account:
            account = self.env["account.account"].create({
                "code": "411300",
                "name": "Créances Service Chambre",
                "account_type": "asset_receivable",
                "company_ids": [(6, 0, [company.id])],
                "reconcile": True,
            })
        return account

    @api.model
    def _ensure_service_income_account(self, company):
        account = self.env["account.account"].search([
            ("code", "=", "707300"),
            ("company_ids", "in", company.id),
        ], limit=1)
        if not account:
            account = self.env["account.account"].create({
                "code": "707300",
                "name": "Ventes services chambre",
                "account_type": "income",
                "company_ids": [(6, 0, [company.id])],
            })
        return account

    # --- Moyen de paiement « Transfert Chambre » --------------------------

    @api.model
    def _ensure_room_charge_method(self, company):
        payment_method = self.search([
            ("is_room_charge", "=", True),
            ("company_id", "=", company.id),
        ], limit=1)

        if not payment_method:
            account = company._x_hotel_account("extras_receivable")

            journal = self.env["account.journal"].search([
                ("code", "=", "TRCH"),
                ("company_id", "=", company.id),
            ], limit=1)
            if not journal:
                journal = self.env["account.journal"].create({
                    "name": "Transferts Chambre",
                    "code": "TRCH",
                    "type": "general",
                    "company_id": company.id,
                    "default_account_id": account.id,
                })

            payment_method = self.create({
                "name": "Transfert Chambre",
                "is_room_charge": True,
                "journal_id": journal.id,
                "company_id": company.id,
                "split_transactions": True,
            })

        configs = self.env["pos.config"].search([("company_id", "=", company.id)])
        configs_missing = configs.filtered(
            lambda c: payment_method not in c.payment_method_ids
        )
        # PdV par PdV : une config client invalide (ex. mode espèces partagé
        # entre deux PdV) ne doit pas faire échouer toute l'installation.
        for config in configs_missing:
            try:
                with self.env.cr.savepoint():
                    config.write({
                        "payment_method_ids": [(4, payment_method.id)],
                    })
            except (ValidationError, UserError) as e:
                _logger.warning(
                    "POS_HOTEL_INTC : impossible d'ajouter '%s' au PdV '%s' (id %s) : %s "
                    "— corriger la configuration du PdV puis ajouter le mode manuellement.",
                    payment_method.name, config.name, config.id, e,
                )

        return payment_method
