def migrate(cr, version):
    env = _get_env(cr)
    calendar = env.ref("booking_engine.calendar_1", raise_if_not_found=False)
    if not calendar:
        return
    rooms = env["resource.resource"].search([("role_ids", "!=", False)])
    rooms.filtered(lambda r: r.calendar_id != calendar).write({"calendar_id": calendar.id})


def _get_env(cr):
    from odoo import api, SUPERUSER_ID
    return api.Environment(cr, SUPERUSER_ID, {})