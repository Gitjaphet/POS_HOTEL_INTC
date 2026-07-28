from odoo import api, models


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    def _get_room_orders_to_resync(self):
        """Commandes impactées par des slots 'chambre' parmi self."""
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
            order.write({
                "rental_start_date": min(room_slots.mapped("start_datetime")),
                "rental_return_date": max(room_slots.mapped("end_datetime")),
            })

    @api.model_create_multi
    def create(self, vals_list):
        slots = super().create(vals_list)
        orders = slots._get_room_orders_to_resync()
        if orders:
            self._sync_room_rental_period(orders)
        return slots

    def write(self, vals):
        res = super().write(vals)
        if {"start_datetime", "end_datetime", "sale_line_id"} & vals.keys():
            orders = self._get_room_orders_to_resync()
            if orders:
                self._sync_room_rental_period(orders)
        return res