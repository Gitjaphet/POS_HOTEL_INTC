from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelNightAudit(models.Model):
    _name = "pos.hotel.night.audit"
    _description = "Night audit — clôture et rapprochement comptable d'une journée d'exploitation"
    _order = "date desc"

    name = fields.Char(
        string="Référence",
        required=True,
        default="Nouveau",
        copy=False,
    )
    date = fields.Date(
        string="Journée auditée",
        required=True,
        default=fields.Date.context_today,
    )
    session_ids = fields.Many2many(
        "pos.session",
        string="Sessions couvertes",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("running", "En cours"),
            ("blocked", "Bloqué"),
            ("done", "Clôturé"),
        ],
        string="Statut",
        default="draft",
        required=True,
        copy=False,
    )
    log_ids = fields.One2many(
        "pos.hotel.night.audit.log",
        "audit_id",
        string="Journal d'exécution",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        default=lambda self: self.env.company,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nouveau") == "Nouveau":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "pos.hotel.night.audit"
                ) or "Nouveau"
        return super().create(vals_list)

    def action_run(self):
        self.ensure_one()
        if self.state not in ('draft', 'blocked'):
            raise UserError("Cet audit a déjà été exécuté.")

        self.write({'state': 'running'})
        seq = max(self.log_ids.mapped('sequence'), default=0)

        def log(step_name, status, message):
            nonlocal seq
            seq += 10
            self.env['pos.hotel.night.audit.log'].create({
                'audit_id': self.id,
                'sequence': seq,
                'step_name': step_name,
                'status': status,
                'message': message,
            })

        if self.log_ids:
            log("Nouvelle tentative", "info", "Relance de l'audit après blocage précédent.")

        account_411200 = self.env['account.account'].search([
            ('code', '=', '411200'),
            ('company_ids', 'in', self.company_id.id),
        ], limit=1)
        if not account_411200:
            log("Configuration", "blocked", "Compte 411200 introuvable.")
            self.write({'state': 'blocked'})
            return

        account_411300 = self.env['account.account'].search([
            ('code', '=', '411300'),
            ('company_ids', 'in', self.company_id.id),
        ], limit=1)
        if not account_411300:
            log("Configuration", "blocked", "Compte 411300 introuvable.")
            self.write({'state': 'blocked'})
            return

        settled_charges_all = self.env['pos.hotel.folio.charge'].search([
            ('settlement_payment_id', '!=', False),
        ])
        offset_charges_all = self.env['pos.hotel.folio.charge'].search([
            ('x_invoice_offset_move_id', '!=', False),
        ])
        manual_charges_all = self.env['pos.hotel.folio.charge'].search([
            ('x_manual_income_move_id', '!=', False),
        ])

        all_closed_sessions = self.env['pos.session'].search([
            ('state', '=', 'closed'),
            ('company_id', '=', self.company_id.id),
        ])

        sessions = all_closed_sessions.filtered(
            lambda s: (
                s.move_id.line_ids.filtered(
                    lambda l: l.account_id == account_411200 and not l.reconciled
                )
            ) or (
                settled_charges_all.filtered(
                    lambda c: (c.pos_order_id.session_id == s)
                    or (c.original_charge_id.pos_order_id.session_id == s)
                ).mapped('settlement_payment_id.move_id.line_ids').filtered(
                    lambda l: l.account_id == account_411200 and not l.reconciled
                )
            ) or (
                offset_charges_all.filtered(
                    lambda c: (c.pos_order_id.session_id == s)
                    or (c.original_charge_id.pos_order_id.session_id == s)
                ).mapped('x_invoice_offset_move_id.line_ids').filtered(
                    lambda l: l.account_id == account_411200 and not l.reconciled
                )
            )
        )

        if not sessions:
            log("Sélection des sessions", "info", "Aucune session fermée à auditer.")
        else:
            self.session_ids = sessions
            log("Sélection des sessions", "ok",
                f"{len(sessions)} session(s) fermée(s) trouvée(s) : {', '.join(sessions.mapped('name'))}")

            debit_lines = self.env['account.move.line']
            empty_sessions = []
            for session in sessions:
                if not session.move_id:
                    valid_orders = session.order_ids.filtered(lambda o: o.state != 'cancel')
                    if valid_orders:
                        log("Vérification clôture", "blocked",
                            f"La session {session.name} a {len(valid_orders)} commande(s) valide(s) "
                            "mais aucune écriture comptable (move_id vide).")
                        self.write({'state': 'blocked'})
                        return
                    empty_sessions.append(session.name)
                    continue
                debit_lines |= session.move_id.line_ids.filtered(
                    lambda l: l.account_id == account_411200
                )
            if empty_sessions:
                log("Vérification clôture", "info",
                    f"{len(empty_sessions)} session(s) sans commande valide, ignorée(s) : "
                    f"{', '.join(empty_sessions)}")

            log("Vérification clôture", "ok",
                f"{len(debit_lines)} ligne(s) 411200 trouvée(s) sur les sessions.")

            charges = settled_charges_all.filtered(
                lambda c: (c.pos_order_id.session_id in sessions)
                or (c.original_charge_id.pos_order_id.session_id in sessions)
            )
            payments = charges.mapped('settlement_payment_id')
            credit_lines = self.env['account.move.line']
            for payment in payments:
                credit_lines |= payment.move_id.line_ids.filtered(
                    lambda l: l.account_id == account_411200
                )

            offset_charges = offset_charges_all.filtered(
                lambda c: (c.pos_order_id.session_id in sessions)
                or (c.original_charge_id.pos_order_id.session_id in sessions)
            )
            offset_moves = offset_charges.mapped('x_invoice_offset_move_id')
            for move in offset_moves:
                credit_lines |= move.line_ids.filtered(
                    lambda l: l.account_id == account_411200
                )

            log("Rapprochement 411200", "info",
                f"{len(payments)} paiement(s) + {len(offset_moves)} compensation(s) facture liée(s) à ces sessions, "
                f"{len(credit_lines)} ligne(s) crédit correspondante(s).")

            unmatched = []
            refund_notes = []
            reconciled_count = 0
            for partner in credit_lines.mapped('partner_id'):
                partner_debits = debit_lines.filtered(lambda l: l.partner_id == partner and not l.reconciled)
                partner_credits = credit_lines.filtered(lambda l: l.partner_id == partner and not l.reconciled)
                if not partner_debits:
                    real_credits = partner_credits.filtered(lambda l: l.credit > 0)
                    refund_debits = partner_credits.filtered(lambda l: l.debit > 0)
                    if real_credits:
                        unmatched.append(
                            f"{partner.name} : {len(real_credits)} paiement(s) sans écriture de session correspondante."
                        )
                    if refund_debits:
                        refund_notes.append(
                            f"{partner.name} : {len(refund_debits)} remboursement(s) post-clôture laissé(s) "
                            "non lettré(s) (session d'origine déjà auditée — comportement normal)."
                        )
                    continue
                (partner_debits + partner_credits).reconcile()
                reconciled_count += len(
                    (partner_debits + partner_credits).filtered('reconciled')
                )

            if unmatched:
                log("Appariement 411200", "blocked", "\n".join(unmatched))
                self.write({'state': 'blocked'})
                return

            log("Appariement 411200", "ok", f"{reconciled_count} ligne(s) rapprochée(s) avec succès.")
            if refund_notes:
                log("Remboursements post-clôture", "info", "\n".join(refund_notes))

            sessions.write({'x_night_audit_id': self.id})

        # --- Charges ajoutées manuellement côté hôtel (extras et services),
        # jamais rattachées à une session POS puisqu'aucune commande POS n'est
        # impliquée. Chaque charge manuelle porte sa propre écriture de revenu
        # (x_manual_income_move_id, débit 411200 ou 411300) à rapprocher
        # indépendamment de toute session, avec son paiement de règlement/
        # remboursement (settlement_payment_id) ou sa compensation de facture
        # (x_invoice_offset_move_id). Traité pour les 2 comptes (extras et
        # services), rapprochement par partenaire ET par compte (jamais
        # d'appariement croisé entre les deux types de créance).
        manual_accounts = account_411200 + account_411300
        manual_debit_lines = manual_charges_all.mapped('x_manual_income_move_id.line_ids').filtered(
            lambda l: l.account_id in manual_accounts and not l.reconciled
        )
        manual_credit_lines = self.env['account.move.line']
        manual_credit_lines |= manual_charges_all.mapped('settlement_payment_id.move_id.line_ids').filtered(
            lambda l: l.account_id in manual_accounts and not l.reconciled
        )
        manual_credit_lines |= manual_charges_all.mapped('x_invoice_offset_move_id.line_ids').filtered(
            lambda l: l.account_id in manual_accounts and not l.reconciled
        )

        if manual_debit_lines or manual_credit_lines:
            log("Rapprochement charges manuelles", "info",
                f"{len(manual_debit_lines)} ligne(s) débit, {len(manual_credit_lines)} ligne(s) crédit "
                "issues de charges ajoutées manuellement (extras/services).")

            manual_unmatched = []
            manual_refund_notes = []
            manual_reconciled_count = 0
            for account in manual_accounts:
                account_lines = (manual_debit_lines + manual_credit_lines).filtered(
                    lambda l: l.account_id == account
                )
                for partner in account_lines.mapped('partner_id'):
                    partner_debits = manual_debit_lines.filtered(
                        lambda l: l.partner_id == partner and l.account_id == account and not l.reconciled
                    )
                    partner_credits = manual_credit_lines.filtered(
                        lambda l: l.partner_id == partner and l.account_id == account and not l.reconciled
                    )
                    if not partner_debits:
                        real_credits = partner_credits.filtered(lambda l: l.credit > 0)
                        refund_debits = partner_credits.filtered(lambda l: l.debit > 0)
                        if real_credits:
                            manual_unmatched.append(
                                f"{partner.name} ({account.code}) : {len(real_credits)} paiement(s) "
                                "sans écriture correspondante."
                            )
                        if refund_debits:
                            manual_refund_notes.append(
                                f"{partner.name} ({account.code}) : {len(refund_debits)} remboursement(s) "
                                "laissé(s) non lettré(s)."
                            )
                        continue
                    (partner_debits + partner_credits).reconcile()
                    manual_reconciled_count += len(
                        (partner_debits + partner_credits).filtered('reconciled')
                    )

            if manual_unmatched:
                log("Appariement charges manuelles", "blocked", "\n".join(manual_unmatched))
                self.write({'state': 'blocked'})
                return

            log("Appariement charges manuelles", "ok",
                f"{manual_reconciled_count} ligne(s) rapprochée(s) avec succès.")
            if manual_refund_notes:
                log("Remboursements post-clôture (manuel)", "info", "\n".join(manual_refund_notes))

        self.write({'state': 'done'})
        log("Clôture", "ok",
            f"Night audit {self.name} clôturé, {len(sessions)} session(s) marquée(s) auditée(s).")
        
class PosHotelNightAuditLog(models.Model):
    _name = "pos.hotel.night.audit.log"
    _description = "Ligne du journal d'exécution d'un night audit"
    _order = "sequence, id"

    audit_id = fields.Many2one(
        "pos.hotel.night.audit",
        string="Night audit",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Ordre", default=10)
    step_name = fields.Char(string="Étape", required=True)
    status = fields.Selection(
        [
            ("ok", "OK"),
            ("blocked", "Bloqué"),
            ("info", "Information"),
        ],
        string="Résultat",
        required=True,
    )
    message = fields.Text(string="Détail")