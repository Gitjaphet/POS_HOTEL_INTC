from odoo import models


class PlanningSlot(models.Model):
    _inherit = 'planning.slot'

    def action_create_order(self):
        self.ensure_one()
        action = super().action_create_order()
        if self.role_id.x_is_a_room_offer:
            context = dict(action.get('context') or {})
            context['default_room_slot_id'] = self.id
            action['context'] = context
        return action