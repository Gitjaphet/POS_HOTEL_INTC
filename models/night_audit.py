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