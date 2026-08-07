def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env["res.company"].search([]):
        env["pos.payment.method"]._ensure_extras_income_account(company)