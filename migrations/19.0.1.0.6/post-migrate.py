def migrate(cr, version):
    env = _get_env(cr)
    payment_methods = env["pos.payment.method"].search([("is_room_charge", "=", True)])
    if payment_methods:
        payment_methods.write({
            "split_transactions": True,
            "sequence": 10,
        })


def _get_env(cr):
    from odoo import api, SUPERUSER_ID
    return api.Environment(cr, SUPERUSER_ID, {})