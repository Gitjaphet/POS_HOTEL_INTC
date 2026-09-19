from datetime import timedelta

import pytz

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
                slot.color = 4  # bleu
            elif slot.x_stay_status == 'checked_out':
                slot.color = 5  # violet
            else:
                slot.color = 10  # vert (pending, confirmé pas encore check-in)

    def _compute_display_name(self):
        super()._compute_display_name()
        for slot in self:
            order = slot.sale_line_id.order_id
            if not order:
                continue
            # Règle 💰/✅ centralisée sur le folio (sale.order) pour rester
            # identique aux compteurs du tableau de bord du planning.
            payment_state = order._get_folio_payment_state()
            if payment_state == 'paid':
                slot.display_name = f"\u2705 {slot.display_name}"
            elif payment_state == 'partial':
                slot.display_name = f"\U0001F4B0 {slot.display_name}"

    @api.model
    def get_hotel_planning_stats(self, period_start=None, period_stop=None):
        """Compteurs du tableau de bord affiché au-dessus du planning hôtel.

        Tous les compteurs de chambres sont calculés à la date du JOUR
        (fuseau de l'utilisateur), pas sur la période affichée : un
        réceptionniste veut savoir l'état de l'hôtel maintenant, pas une
        moyenne du mois. Seul 'cancelled' porte sur la période affichée,
        une annulation étant un événement et non un état.

        :param period_start: début de la période affichée (str ou datetime)
        :param period_stop: fin de la période affichée
        :return: dict de compteurs, consommé par le composant JS des contrôles
        """
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        now_local = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_stop_local = day_start_local + timedelta(days=1)
        # Repasse en UTC naïf : c'est le format de stockage des datetimes Odoo.
        day_start = day_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        day_stop = day_stop_local.astimezone(pytz.UTC).replace(tzinfo=None)

        room_domain = [('role_id.x_is_a_room_offer', '=', True)]

        # Une seule lecture des séjours couvrant aujourd'hui : le volume est
        # borné par le nombre de chambres, donc le coût ne grandit pas avec
        # l'historique. Tous les compteurs du jour en dérivent en mémoire.
        slots_today = self.search(room_domain + [
            ('start_datetime', '<', day_stop),
            ('end_datetime', '>=', day_start),
        ])
        occupied = slots_today.filtered(lambda s: s.x_stay_status == 'checked_in')
        reserved = slots_today.filtered(lambda s: s.x_stay_status == 'pending')
        departed = slots_today.filtered(lambda s: s.x_stay_status == 'checked_out')

        # Une chambre dont le client est parti est de nouveau attribuable :
        # seuls 'pending' et 'checked_in' immobilisent la ressource.
        busy_slots = occupied | reserved
        busy_rooms = len(set(busy_slots.mapped('resource_id').ids))
        Resource = self.env['resource.resource']
        total_rooms = Resource.search_count(Resource._get_room_resource_domain())

        # Règle 💰/✅ empruntée au folio pour rester alignée sur les pastilles.
        paid_rooms = sum(
            1 for slot in busy_slots
            if slot.sale_line_id.order_id
            and slot.sale_line_id.order_id._get_folio_payment_state() != 'none'
        )

        arrivals = self.search_count(room_domain + [
            ('start_datetime', '>=', day_start),
            ('start_datetime', '<', day_stop),
        ])
        departures = self.search_count(room_domain + [
            ('end_datetime', '>=', day_start),
            ('end_datetime', '<', day_stop),
        ])

        # Les séjours annulés sont supprimés du planning (sale.order
        # _action_cancel -> unlink des slots), volontairement : un slot
        # fantôme bloquerait la contrainte anti-double-booking lors d'une
        # nouvelle réservation. Le compteur se prend donc sur les commandes.
        cancelled = 0
        if period_start and period_stop:
            cancelled = self.env['sale.order'].search_count([
                ('state', '=', 'cancel'),
                ('order_line.x_is_a_room_offer', '=', True),
                ('rental_start_date', '<', fields.Datetime.to_datetime(period_stop)),
                ('rental_return_date', '>=', fields.Datetime.to_datetime(period_start)),
            ])

        return {
            'reference_date': fields.Date.to_string(day_start_local.date()),
            'occupied': len(occupied),
            'reserved': len(reserved),
            'departed': len(departed),
            'free': max(total_rooms - busy_rooms, 0),
            'total_rooms': total_rooms,
            'arrivals': arrivals,
            'departures': departures,
            'paid': paid_rooms,
            'cancelled': cancelled,
        }