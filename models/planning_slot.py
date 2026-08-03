from odoo import fields, models


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