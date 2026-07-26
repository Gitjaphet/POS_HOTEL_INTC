def post_init_hook(env):
    for company in env["res.company"].search([]):
        env["pos.payment.method"]._ensure_room_charge_method(company)
    _fix_room_calendars(env)


def _fix_room_calendars(env):
    calendar = env.ref("booking_engine.calendar_1", raise_if_not_found=False)
    if not calendar:
        return
    rooms = env["resource.resource"].search([("role_ids", "!=", False)])
    rooms.filtered(lambda r: r.calendar_id != calendar).write({"calendar_id": calendar.id})