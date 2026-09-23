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
    # État de paiement du folio, exposé à la vue Gantt pour l'icône des
    # pastilles (fa-money si partiel, badge vert si payé). Non stocké : dépend
    # de factures, acomptes, extras et paiements POS, trop de sources pour des
    # @api.depends fiables. La règle vit dans sale.order._get_folio_payment_state().
    x_payment_state = fields.Selection(
        [('none', "Non payé"), ('partial', "Acompte / partiel"), ('paid', "Payé")],
        string="État de paiement",
        compute='_compute_x_payment_state',
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


    @api.depends('x_stay_status', 'sale_line_id')
    def _compute_color(self):
        for slot in self:
            if not slot.sale_line_id:
                slot.color = 0  # gris : devis, aucune commande liée
            elif slot.x_stay_status == 'checked_in':
                slot.color = 4  # bleu
            elif slot.x_stay_status == 'checked_out':
                slot.color = 5  # violet
            else:
                slot.color = 10  # vert (pending, confirmé pas encore check-in)

    def _compute_x_payment_state(self):
        # Règle centralisée sur le folio (sale.order) pour rester identique
        # aux compteurs du tableau de bord du planning.
        for slot in self:
            order = slot.sale_line_id.order_id
            slot.x_payment_state = order._get_folio_payment_state() if order else 'none'

    @api.model
    def get_hotel_planning_stats(self, period_start=None, period_stop=None, reference_date=None):
        """Compteurs du tableau de bord affiché au-dessus du planning hôtel.

        États du JOUR (fuseau de l'utilisateur) : occupées, réservées, libres,
        départs à venir. Un réceptionniste veut l'état de l'hôtel maintenant,
        quelle que soit la période affichée.
        Événements de la PÉRIODE affichée : arrivées, départs, payées,
        annulées. Ce sont des faits datés, comptés sur ce que l'utilisateur regarde.

        :param period_start: début de la période affichée (str ou datetime)
        :param period_stop: fin de la période affichée
        :return: dict de compteurs, consommé par le patch JS de PlanningGanttRenderer
        """
        
        # reference_date permet de projeter les compteurs sur une autre date
        # (test, ou future sélection de date dans le planning) ; par défaut
        # c'est le jour courant dans le fuseau de l'utilisateur.
        now_local = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        if reference_date:
            ref = fields.Date.to_date(reference_date)
            now_local = now_local.replace(year=ref.year, month=ref.month, day=ref.day)
        day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_stop_local = day_start_local + timedelta(days=1)
        # Repasse en UTC naïf : c'est le format de stockage des datetimes Odoo.
        day_start = day_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        day_stop = day_stop_local.astimezone(pytz.UTC).replace(tzinfo=None)

        # Les devis (séjours sans commande liée, pastilles grises) sont exclus
        # de tous les compteurs : seules les vraies réservations comptent.
        room_domain = [('role_id.x_is_a_room_offer', '=', True), ('sale_line_id', '!=', False)]

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


        # Départs à venir : séjours encore en cours se terminant dans les
        # 2 prochains jours. Toujours relatif à aujourd'hui, jamais à la
        # période affichée — "dans 2 jours" n'a de sens que depuis maintenant.
        soon = day_start + timedelta(days=2)
        upcoming_departures = self.search_count(room_domain + [
            ('end_datetime', '>=', day_start),
            ('end_datetime', '<', soon),
            ('x_stay_status', '!=', 'checked_out'),
        ])

        # Événements de la période affichée, par opposition aux états du jour
        # ci-dessus : une arrivée, un départ ou une annulation est un fait
        # daté, qu'on compte donc sur ce que l'utilisateur regarde.
        arrivals = departures = cancelled = paid = confirmed = 0
        if period_start and period_stop:
            p_start = fields.Datetime.to_datetime(period_start)
            p_stop = fields.Datetime.to_datetime(period_stop)
            arrivals = self.search_count(room_domain + [
                ('start_datetime', '>=', p_start),
                ('start_datetime', '<', p_stop),
            ])
            departures = self.search_count(room_domain + [
                ('end_datetime', '>=', p_start),
                ('end_datetime', '<', p_stop),
            ])
            # Les séjours annulés sont supprimés du planning (sale.order
            # _action_cancel -> unlink des slots) : un slot fantôme bloquerait
            # la contrainte anti-double-booking. Le compteur passe donc par
            # les commandes.
            cancelled = self.env['sale.order'].search_count([
                ('state', '=', 'cancel'),
                ('order_line.x_is_a_room_offer', '=', True),
                ('rental_start_date', '<', p_stop),
                ('rental_return_date', '>=', p_start),
            ])

            # Payées : séjours touchant la période qui portent un badge de
            # paiement (acompte/partiel ou soldé), soit exactement les
            # pastilles à badge jaune ou vert visibles sur le Gantt.
            period_slots = self.search(room_domain + [
                ('start_datetime', '<', p_stop),
                ('end_datetime', '>=', p_start),
            ])
            # Confirmées : réservations pas encore arrivées (pastilles vertes),
            # comptées par folio comme sur Booking (3 chambres = 1).
            confirmed = len(period_slots.filtered(lambda s: s.x_stay_status == 'pending').sale_line_id.order_id)
            paid = len(period_slots.filtered(lambda s: s.x_payment_state != 'none'))

        return {
            'reference_date': fields.Date.to_string(day_start_local.date()),
            'occupied': len(occupied),
            'reserved': len(reserved),
            'departed': len(departed),
            'free': max(total_rooms - busy_rooms, 0),
            'total_rooms': total_rooms,
            'arrivals': arrivals,
            'departures': departures,
            'upcoming_departures': upcoming_departures,
            'paid': paid,
            'confirmed': confirmed,
            'cancelled': cancelled,
        }