from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    x_guest_registration_scope = fields.Selection(
        related="company_id.x_guest_registration_scope", readonly=False)
    x_guest_registration_mode = fields.Selection(
        related="company_id.x_guest_registration_mode", readonly=False)
    x_guest_require_nationality = fields.Boolean(
        related="company_id.x_guest_require_nationality", readonly=False)
    x_guest_require_document = fields.Boolean(
        related="company_id.x_guest_require_document", readonly=False)
    x_guest_require_birth_date = fields.Boolean(
        related="company_id.x_guest_require_birth_date", readonly=False)
    x_guest_require_travel = fields.Boolean(
        related="company_id.x_guest_require_travel", readonly=False)
