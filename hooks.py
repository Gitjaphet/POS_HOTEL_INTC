def post_init_hook(env):
    for company in env["res.company"].search([]):
        env["pos.payment.method"]._ensure_room_charge_method(company)
        env["pos.payment.method"]._ensure_extras_income_account(company)
    _fix_room_calendars(env)
    _fix_booking_engine_order_form_view(env)


def _fix_room_calendars(env):
    calendar = env.ref("booking_engine.calendar_1", raise_if_not_found=False)
    if not calendar:
        return
    rooms = env["resource.resource"].search([("role_ids", "!=", False)])
    rooms.filtered(lambda r: r.calendar_id != calendar).write({"calendar_id": calendar.id})


def _fix_booking_engine_order_form_view(env):
    action = env.ref("booking_engine.booking_engine_rooms_order_action", raise_if_not_found=False)
    hotel_view = env.ref("POS_HOTEL_INTC.sale_order_primary_view_pos_hotel_intc", raise_if_not_found=False)
    if not action or not hotel_view:
        return
    action_view = env["ir.actions.act_window.view"].search([
        ("act_window_id", "=", action.id),
        ("view_mode", "=", "form"),
    ])
    if action_view:
        action_view.view_id = hotel_view.id