from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _planning_slot_vals_list_per_sol(self):
        vals_list_per_sol = super()._planning_slot_vals_list_per_sol()
        room_slot_id = self.env.context.get('default_room_slot_id')
        if not room_slot_id:
            return vals_list_per_sol

        room_slot = self.env['planning.slot'].browse(room_slot_id).exists()
        if not room_slot or room_slot.sale_line_id:
            return vals_list_per_sol

        for sol, vals_list in vals_list_per_sol.items():
            if sol.product_id.planning_role_id.x_is_a_room_offer:
                room_slot.write({
                    'sale_line_id': sol.id,
                    'sale_order_id': sol.order_id.id,
                    'state': 'published',
                })
                vals_list_per_sol[sol] = []  # empêche la création d'un slot en plus

        return vals_list_per_sol