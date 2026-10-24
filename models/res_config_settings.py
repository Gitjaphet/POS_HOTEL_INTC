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
    x_police_card_footer = fields.Text(
        related="company_id.x_police_card_footer", readonly=False)

    # Comptes de l'hôtel (res.company._x_hotel_account).
    x_hotel_extras_receivable_account_id = fields.Many2one(
        related="company_id.x_hotel_extras_receivable_account_id", readonly=False,
        domain="[('account_type', '=', 'asset_receivable'), ('company_ids', 'in', company_id)]")
    x_hotel_services_receivable_account_id = fields.Many2one(
        related="company_id.x_hotel_services_receivable_account_id", readonly=False,
        domain="[('account_type', '=', 'asset_receivable'), ('company_ids', 'in', company_id)]")
    x_hotel_extras_income_account_id = fields.Many2one(
        related="company_id.x_hotel_extras_income_account_id", readonly=False,
        domain="[('account_type', 'in', ('income', 'income_other')), ('company_ids', 'in', company_id)]")
    x_hotel_services_income_account_id = fields.Many2one(
        related="company_id.x_hotel_services_income_account_id", readonly=False,
        domain="[('account_type', 'in', ('income', 'income_other')), ('company_ids', 'in', company_id)]")
