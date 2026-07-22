def post_init_hook(env):
    for company in env["res.company"].search([]):
        env["pos.payment.method"]._ensure_room_charge_method(company)