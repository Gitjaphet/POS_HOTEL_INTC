from odoo import api, models


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    def _get_room_orders_to_resync(self):
        room_slots = self.filtered(lambda s: s.role_id.x_is_a_room_offer and s.sale_line_id)
        return room_slots.sale_line_id.order_id

    def _sync_room_rental_period(self, orders):
        for order in orders:
            room_slots = self.env["planning.slot"].search([
                ("sale_line_id", "in", order.order_line.ids),
                ("role_id.x_is_a_room_offer", "=", True),
                ("start_datetime", "!=", False),
                ("end_datetime", "!=", False),
            ])
            if not room_slots:
                continue
            new_start = min(room_slots.mapped("start_datetime"))
            new_end = max(room_slots.mapped("end_datetime"))
            if order.rental_start_date == new_start and order.rental_return_date == new_end:
                continue  # rien à faire : évite le write inutile qui redéclenche la boucle
            order.with_context(skip_room_rental_sync=True).write({
                "rental_start_date": new_start,
                "rental_return_date": new_end,
            })

    @api.model_create_multi
    def create(self, vals_list):
        slots = super().create(vals_list)
        if not self.env.context.get("skip_room_rental_sync"):
            orders = slots._get_room_orders_to_resync()
            if orders:
                self._sync_room_rental_period(orders)
        return slots

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_room_rental_sync") and {"start_datetime", "end_datetime", "sale_line_id"} & vals.keys():
            orders = self._get_room_orders_to_resync()
            if orders:
                self._sync_room_rental_period(orders)
        return res