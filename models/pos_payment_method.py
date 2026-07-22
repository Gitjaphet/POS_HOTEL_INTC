from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    is_room_charge = fields.Boolean(
        string="Transfert vers chambre",
        help="Si activé, ce moyen de paiement ouvre la recherche de chambre/séjour "
             "au lieu d'encaisser directement. Le montant est imputé au folio du client.",
    )

    @api.model
    def _ensure_room_charge_method(self, company):
        existing = self.search([
            ("is_room_charge", "=", True),
            ("company_id", "=", company.id),
        ], limit=1)
        if existing:
            return existing

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

        return self.create({
            "name": "Transfert Chambre",
            "is_room_charge": True,
            "journal_id": journal.id,
            "company_id": company.id,
            "sequence": 1,
        })