from odoo import models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _planning_slot_vals_list_per_sol(self):
        vals_list_per_sol = super()._planning_slot_vals_list_per_sol()
        for sol, vals_list in vals_list_per_sol.items():
            role = sol.product_id.planning_role_id
            if not (role.x_is_a_room_offer and vals_list):
                continue

            orphan = self.env['planning.slot'].search([
                ('resource_id', 'in', role.resource_ids.ids),
                ('sale_line_id', '=', False),
                ('start_datetime', '<=', sol.return_date),
                ('end_datetime', '>=', sol.start_date),
            ], order='id desc', limit=1)

            if orphan:
                orphan.write({
                    'sale_line_id': sol.id,
                    'sale_order_id': sol.order_id.id,
                    'state': 'published',
                })
                vals_list_per_sol[sol] = []

        return vals_list_per_sol