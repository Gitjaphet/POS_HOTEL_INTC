from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.misc import clean_context

PREPAID_LABEL = "Réglé pendant le séjour"


class AccountMove(models.Model):
    """Facture finale complète : consommations déjà réglées (à la réception
    ou au POS) incluses dans la facture, avec leur paiement déduit.

    Une consommation réglée a déjà son revenu (session POS ou ajout manuel)
    et son encaissement. Sur la facture, elle crée un second revenu et une
    créance client : l'écriture « Réglé pendant le séjour », une par facture,
    passée à la confirmation, neutralise les deux (débit 707200|707300 par
    consommation / crédit du compte client de la facture, lettré avec elle).
    Les comptes 411200/411300, les règlements d'origine et le night audit ne
    sont pas touchés (23/10/2026).

    - Facture remise en brouillon puis reconfirmée : écriture réutilisée et
      relettrée.
    - Facture annulée ou extournée : écriture contrepassée (écriture neuve
      datée du jour), comme les compensations.
    """
    _inherit = "account.move"

    x_hotel_prepaid_move_id = fields.Many2one(
        "account.move",
        string="Écriture « Réglé pendant le séjour »",
        copy=False,
        readonly=True,
    )
    x_hotel_prepaid_reversal_ids = fields.Many2many(
        "account.move",
        "account_move_hotel_prepaid_reversal_rel",
        "invoice_id",
        "move_id",
        string="Contrepassations « Réglé pendant le séjour »",
        copy=False,
        readonly=True,
    )

    def _x_prepaid_charges(self):
        self.ensure_one()
        return self.env["pos.hotel.folio.charge"].search([
            ("x_invoice_id", "=", self.id),
            ("payment_status", "in", ("settled", "paid_pos")),
            ("is_refund", "=", False),
        ])

    def _x_reconcile_prepaid(self):
        self.ensure_one()
        credit = self.x_hotel_prepaid_move_id.line_ids.filtered(
            lambda l: l.credit > 0 and not l.reconciled
        )
        receivable = self.line_ids.filtered(
            lambda l: l.account_id in credit.account_id and l.debit > 0 and not l.reconciled
        )
        if credit and receivable:
            (credit + receivable).reconcile()

    def _x_post_prepaid_entry(self):
        Charge = self.env["pos.hotel.folio.charge"]
        for invoice in self:
            if invoice.x_hotel_prepaid_move_id:
                invoice._x_reconcile_prepaid()
                continue
            charges = invoice._x_prepaid_charges().filtered(
                lambda c: not c.currency_id.is_zero(c.amount_net)
            )
            if not charges:
                continue
            receivable_line = invoice.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable"
            )[:1]
            if not receivable_line:
                continue
            company_id = invoice.company_id.id
            extras_income = Charge._x_find_account("707200", company_id, "Ventes extras chambre")
            services_income = Charge._x_find_account("707300", company_id, "Ventes services chambre")
            journal = self.env["account.journal"].search([
                ("type", "=", "general"),
                ("company_id", "=", company_id),
            ], limit=1)
            if not journal:
                raise UserError("Aucun journal 'Opérations diverses' trouvé.")
            partner = invoice.commercial_partner_id
            lines = [
                Command.create({
                    "account_id": (services_income if c.is_service else extras_income).id,
                    "partner_id": partner.id,
                    "name": c.name,
                    "debit": c.amount_net,
                    "credit": 0.0,
                })
                for c in charges
            ]
            lines.append(Command.create({
                "account_id": receivable_line.account_id.id,
                "partner_id": partner.id,
                "name": PREPAID_LABEL,
                "debit": 0.0,
                "credit": sum(charges.mapped("amount_net")),
            }))
            move = self.env["account.move"].with_context(
                clean_context(self.env.context)
            ).create({
                "move_type": "entry",
                "journal_id": journal.id,
                "date": fields.Date.context_today(self),
                "ref": f"{PREPAID_LABEL} — {invoice.name}",
                "line_ids": lines,
            })
            move.action_post()
            invoice.x_hotel_prepaid_move_id = move
            invoice._x_reconcile_prepaid()

    def _x_cancel_prepaid_entry(self, reason):
        for invoice in self.filtered("x_hotel_prepaid_move_id"):
            move = invoice.x_hotel_prepaid_move_id
            reverse = move.with_context(clean_context(self.env.context))._reverse_moves([{
                "date": fields.Date.context_today(self),
                "ref": f"Contrepassation {PREPAID_LABEL} — {invoice.name} ({reason})",
            }])
            reverse.action_post()
            credit = move.line_ids.filtered(lambda l: l.credit > 0 and not l.reconciled)
            debit = reverse.line_ids.filtered(
                lambda l: l.debit > 0 and l.account_id in credit.account_id and not l.reconciled
            )
            if credit and debit:
                (credit + debit).reconcile()
            invoice.write({
                "x_hotel_prepaid_reversal_ids": [Command.link(reverse.id)],
                "x_hotel_prepaid_move_id": False,
            })
