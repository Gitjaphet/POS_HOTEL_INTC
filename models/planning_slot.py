from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PlanningSlot(models.Model):
    _inherit = 'planning.slot'

    x_stay_status = fields.Selection(
        [
            ('pending', 'À enregistrer'),
            ('checked_in', 'Enregistré'),
            ('checked_out', 'Parti'),
        ],
        string="Statut du séjour",
        default='pending',
        required=True,
        help="État réel du séjour pour cette chambre précise, indépendant "
             "des quantités globales natives (qty_delivered/qty_returned) "
             "qui ne distinguent pas quelle ressource a été traitée.",
    )
    x_checked_in_at = fields.Datetime(
        string="Enregistré le",
        help="Horodatage informatif de l'enregistrement (check-in) de cette "
             "chambre. N'est jamais utilisé comme source de vérité pour la "
             "logique métier — voir x_stay_status.",
    )
    x_checked_out_at = fields.Datetime(
        string="Départ le",
        help="Horodatage informatif du départ (check-out) de cette chambre. "
             "N'est jamais utilisé comme source de vérité pour la logique "
             "métier — voir x_stay_status.",
    )

    def action_create_order(self):
        action = super().action_create_order()
        if self.role_id.x_is_a_room_offer:
            hotel_view = self.env.ref(
                'POS_HOTEL_INTC.sale_order_primary_view_pos_hotel_intc',
                raise_if_not_found=False,
            )
            if hotel_view:
                action['views'] = [
                    (hotel_view.id, view_type) if view_type == 'form' else (view_id, view_type)
                    for view_id, view_type in action['views']
                ]
                action['view_id'] = hotel_view.id
        return action



    @api.constrains('start_datetime', 'end_datetime', 'resource_id')
    def _check_room_double_booking(self):
        for slot in self:
            if not slot.role_id.x_is_a_room_offer:
                continue
            if not (slot.resource_id and slot.start_datetime and slot.end_datetime):
                continue
            conflicting = self.search([
                ('id', '!=', slot.id),
                ('resource_id', '=', slot.resource_id.id),
                ('x_stay_status', '!=', 'checked_out'),
                ('start_datetime', '<', slot.end_datetime),
                ('end_datetime', '>', slot.start_datetime),
            ])
            if conflicting:
                raise ValidationError(
                    f"La chambre {slot.resource_id.name} est déjà réservée sur "
                    f"une période qui chevauche celle-ci ({slot.start_datetime} → "
                    f"{slot.end_datetime}). Choisissez une autre chambre ou d'autres dates."
                )


    @api.depends('x_stay_status')
    def _compute_color(self):
        for slot in self:
            if slot.x_stay_status == 'checked_in':
                slot.color = 10  # vert
            elif slot.x_stay_status == 'checked_out':
                slot.color = 5  # violet
            else:
                slot.color = 4  # bleu clair (confirmé, pas encore check-in)