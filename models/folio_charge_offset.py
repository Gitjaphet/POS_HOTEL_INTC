from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.misc import clean_context


class PosHotelFolioCharge(models.Model):
    """Écriture de compensation d'une consommation facturée.

    Une consommation a DÉJÀ généré son revenu (session POS : 707000 ; ajout
    manuel : 707200/707300) et sa créance (411200/411300). Mise sur une
    facture, elle génère un second revenu (707200/707300) : la compensation
    (débit 707200|707300 / crédit 411200|411300) neutralise ce doublon et
    éteint la créance d'origine, rapprochée tout de suite si possible, sinon
    par le night audit (qui la retrouve par x_invoice_offset_move_id).

    - Passée à la CONFIRMATION de la facture (account.move._post), jamais au
      brouillon ; une facture remise en brouillon puis reconfirmée réutilise
      sa compensation (23/10/2026).
    - Contrepassée quand la facture confirmée est annulée ou extournée
      (account.move._x_hotel_cancel_offsets) : écriture NEUVE datée du jour,
      jamais de modification de l'écriture d'origine ni d'un audit clôturé.
      La contrepassation rouvre la créance (débit 411200|411300), rapprochée
      avec la prochaine compensation ou le règlement, y compris par le night
      audit (x_invoice_offset_reversal_ids).
    """
    _inherit = "pos.hotel.folio.charge"

    x_invoice_offset_reversal_ids = fields.Many2many(
        "account.move",
        "pos_hotel_charge_offset_reversal_rel",
        "charge_id",
        "move_id",
        string="Contrepassations de compensation",
        copy=False,
        readonly=True,
        help="Écritures contrepassant une compensation de facture, quand la "
             "facture a été annulée ou extournée. Elles rouvrent la créance de "
             "la consommation ; le night audit les rapproche.",
    )

    def _x_find_account(self, code, company_id, label):
        account = self.env["account.account"].search([
            ("code", "=", code),
            ("company_ids", "in", company_id),
        ], limit=1)
        if not account:
            raise UserError(f"Le compte {code} ({label}) est introuvable.")
        return account

    def _x_post_invoice_offset(self, invoice):
        """Compensation de chaque consommation de `self` facturée sur
        `invoice`, si elle n'en a pas encore (idempotent)."""
        charges = self.filtered(lambda c: not c.x_invoice_offset_move_id)
        if not charges:
            return
        company_id = invoice.company_id.id or self.env.company.id
        extras_income = self._x_find_account("707200", company_id, "Ventes extras chambre")
        services_income = self._x_find_account("707300", company_id, "Ventes services chambre")
        extras_receivable = self._x_find_account("411200", company_id, "Créances Transferts Chambre")
        services_receivable = self._x_find_account("411300", company_id, "Créances Service Chambre")
        journal = self.env["account.journal"].search([
            ("type", "=", "general"),
            ("company_id", "=", company_id),
        ], limit=1)
        if not journal:
            raise UserError("Aucun journal 'Opérations diverses' trouvé.")

        for charge in charges:
            income_account = services_income if charge.is_service else extras_income
            receivable_account = services_receivable if charge.is_service else extras_receivable
            partner = charge.partner_id or charge.sale_order_id.partner_id
            # Contexte nettoyé et type explicite : appelée pendant la
            # confirmation d'une facture client, la création héritait de
            # default_move_type=out_invoice et devenait une facture
            # (« écriture non équilibrée », 23/10/2026).
            offset_move = self.env["account.move"].with_context(
                clean_context(self.env.context)
            ).create({
                "move_type": "entry",
                "journal_id": journal.id,
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
            # Dette à éteindre : celle d'origine (session POS ou ajout
            # manuel), ou celle rouverte par une contrepassation précédente.
            candidates = charge.x_invoice_offset_reversal_ids.line_ids
            session = (
                charge.pos_order_id.session_id
                or charge.original_charge_id.pos_order_id.session_id
            )
            if session and session.move_id:
                candidates |= session.move_id.line_ids
            elif charge.x_manual_income_move_id:
                candidates |= charge.x_manual_income_move_id.line_ids
            matching_debit = candidates.filtered(
                lambda l: l.account_id == receivable_account
                and l.partner_id == partner
                and l.debit > 0
                and not l.reconciled
            )
            if matching_debit:
                (matching_debit + new_credit_line).reconcile()

    def _x_cancel_invoice_offset(self, reason):
        """Contrepasse la compensation de chaque consommation de `self` dont
        la facture a été annulée ou extournée. La consommation repart sans
        compensation : la prochaine facture lui en créera une neuve."""
        for charge in self.filtered("x_invoice_offset_move_id"):
            offset = charge.x_invoice_offset_move_id
            reverse = offset.with_context(clean_context(self.env.context))._reverse_moves([{
                "date": fields.Date.context_today(self),
                "ref": f"Contrepassation compensation — {charge.name} ({reason})",
            }])
            reverse.action_post()
            # Compensation pas encore rapprochée : les deux s'annulent entre
            # elles. Sinon, la contrepassation reste une dette ouverte.
            credit = offset.line_ids.filtered(
                lambda l: l.credit > 0 and l.account_id.reconcile and not l.reconciled
            )
            debit = reverse.line_ids.filtered(
                lambda l: l.debit > 0 and l.account_id in credit.account_id and not l.reconciled
            )
            if credit and debit:
                (credit + debit).reconcile()
            charge.write({
                "x_invoice_offset_reversal_ids": [Command.link(reverse.id)],
                "x_invoice_offset_move_id": False,
            })
            charge.sale_order_id.message_post(
                body=f"Compensation {offset.name} contrepassée par {reverse.name} "
                     f"({charge.name}, {reason})."
            )
