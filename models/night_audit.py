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

        self.log_ids.unlink()
        self.write({'state': 'running'})
        seq = 0

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

        account_411200 = self.env['account.account'].search([
            ('code', '=', '411200'),
            ('company_ids', 'in', self.company_id.id),
        ], limit=1)
        if not account_411200:
            log("Configuration", "blocked", "Compte 411200 introuvable.")
            self.write({'state': 'blocked'})
            return

        sessions = self.env['pos.session'].search([
            ('state', '=', 'closed'),
            ('x_night_audit_id', '=', False),
            ('company_id', '=', self.company_id.id),
        ])
        if not sessions:
            log("Sélection des sessions", "info", "Aucune session fermée à auditer.")
            self.write({'state': 'done'})
            return
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

        charges = self.env['pos.hotel.folio.charge'].search([
            ('settlement_payment_id', '!=', False),
        ]).filtered(
            lambda c: (c.pos_order_id.session_id in sessions)
            or (c.original_charge_id.pos_order_id.session_id in sessions)
        )
        payments = charges.mapped('settlement_payment_id')
        credit_lines = self.env['account.move.line']
        for payment in payments:
            credit_lines |= payment.move_id.line_ids.filtered(
                lambda l: l.account_id == account_411200
            )
        log("Rapprochement 411200", "info",
            f"{len(payments)} paiement(s) lié(s) à ces sessions, {len(credit_lines)} ligne(s) crédit correspondante(s).")

        unmatched = []
        reconciled_count = 0
        for partner in credit_lines.mapped('partner_id'):
            partner_debits = debit_lines.filtered(lambda l: l.partner_id == partner and not l.reconciled)
            partner_credits = credit_lines.filtered(lambda l: l.partner_id == partner and not l.reconciled)
            if not partner_debits:
                unmatched.append(
                    f"{partner.name} : {len(partner_credits)} paiement(s) sans écriture de session correspondante."
                )
                continue
            (partner_debits + partner_credits).reconcile()
            reconciled_count += len(partner_debits) + len(partner_credits)

        if unmatched:
            log("Appariement 411200", "blocked", "\n".join(unmatched))
            self.write({'state': 'blocked'})
            return

        log("Appariement 411200", "ok", f"{reconciled_count} ligne(s) rapprochée(s) avec succès.")

        sessions.write({'x_night_audit_id': self.id})
        self.write({'state': 'done'})
        log("Clôture", "ok", f"Night audit {self.name} clôturé, {len(sessions)} session(s) marquée(s) auditée(s).")

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