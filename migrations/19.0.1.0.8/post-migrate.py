def migrate(cr, version):
    env = _get_env(cr)
    action_view = env['ir.actions.act_window.view'].search([
        ('action_id', '=', env.ref('booking_engine.booking_engine_rooms_order_action').id),
        ('view_mode', '=', 'form'),
    ])
    hotel_view = env.ref('POS_HOTEL_INTC.sale_order_primary_view_pos_hotel_intc', raise_if_not_found=False)
    if action_view and hotel_view:
        action_view.view_id = hotel_view.id


def _get_env(cr):
    from odoo import api, SUPERUSER_ID
    return api.Environment(cr, SUPERUSER_ID, {})
