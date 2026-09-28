from datetime import timedelta

import pytz

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError


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

    x_pricelist_id = fields.Many2one(
        'product.pricelist',
        default=lambda self: self.env['product.pricelist'].search(
            [('company_id', 'in', [self.env.company.id, False])], limit=1,
        ),
        string="Liste de prix",
        help="Choisie à la création depuis le planning hôtel et reprise par "
             "« Créer la réservation » : le brouillon affiche le prix sans "
             "attendre le choix du client.",
    )

    # Occupation saisie dès la fenêtre du planning, recopiée sur la ligne de
    # chambre par « Créer la réservation » (comme les dates et le tarif).
    x_adults = fields.Integer(string="Adultes", default=1)
    x_children = fields.Integer(string="Enfants", default=0)

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
            # Pré-remplit les dates de séjour de la ligne chambre. Elles ne sont
            # posées qu'au create() de la ligne : sans ça, le brouillon affiche
            # Début/Fin séjour vides et 0 nuit jusqu'à l'enregistrement.
            for command in action.get('context', {}).get('default_order_line', []):
                if command[0] == Command.CREATE:
                    command[2].update({
                        'x_room_start_date': self.start_datetime,
                        'x_room_return_date': self.end_datetime,
                        'x_adults': self.x_adults,
                        'x_children': self.x_children,
                    })
            # Liste de prix choisie dans la fenêtre du planning : le brouillon
            # calcule le prix de la chambre sans attendre le choix du client.
            if self.x_pricelist_id:
                action.setdefault('context', {})['default_pricelist_id'] = self.x_pricelist_id.id
                action['context']['hotel_locked_pricelist_id'] = self.x_pricelist_id.id
            # Permet au formulaire de commande de supprimer ce créneau si le
            # brouillon est abandonné (voir form_hotel_draft_patch.js).
            action.setdefault('context', {})['hotel_draft_slot_id'] = self.id
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

    def action_open_hotel_folio(self):
        """Ouvre le folio (sale.order) lié avec le formulaire hôtel.

        Appelée par le popover du planning hôtel (bouton « Ouvrir la fiche »).
        Renvoie False pour un devis sans commande liée.
        """
        self.ensure_one()
        order = self.sale_line_id.order_id
        if not order:
            return False
        view = self.env.ref('POS_HOTEL_INTC.sale_order_primary_view_pos_hotel_intc')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': order.id,
            'views': [(view.id, 'form')],
            'target': 'current',
        }

    def action_discard_hotel_draft(self):
        """Supprime le créneau chambre laissé par un brouillon de réservation
        abandonné (« Créer la réservation » enregistre le créneau avant
        d'ouvrir la commande). Sécurité : seuls les créneaux chambre encore
        sans commande sont supprimés ; une vraie réservation n'est jamais touchée.
        """
        self.exists().filtered(
            lambda s: not s.sale_line_id and s.role_id.x_is_a_room_offer
        ).unlink()
        return True

    def write(self, vals):
        # Changement de chambre vers un autre type (glisser-déposer, édition) :
        # refusé ici, avant écriture. Le changement de type passe par l'action
        # « Changer de chambre » (contexte x_room_type_change).
        if 'resource_id' in vals and not self.env.context.get('x_room_type_change'):
            self._x_check_room_type(vals['resource_id'])
        res = super().write(vals)
        # Planning → commande : une barre de chambre déplacée ou étirée à la
        # souris met à jour les dates de sa ligne (nuits et prix). Les
        # écritures faites par la ligne elle-même (rental_order_updated,
        # x_syncing_room_dates) sont ignorées : c'est le garde anti-boucle.
        if (
            ('start_datetime' in vals or 'end_datetime' in vals)
            and not self.env.context.get('rental_order_updated')
            and not self.env.context.get('x_syncing_room_dates')
        ):
            self._x_sync_room_line_dates(
                start_changed='start_datetime' in vals,
                end_changed='end_datetime' in vals,
            )
        # Changement de chambre (glisser-déposer vertical) : la description de
        # la ligne (« Chambre 302 — 4 Nights ») est un champ stocké qui ne
        # dépend pas de la ressource ; on la remet en file de recalcul, comme
        # _sync_existing_room_slots_dates le fait pour les dates.
        if 'resource_id' in vals and not self.env.context.get('x_syncing_room_dates'):
            lines = self.filtered(
                lambda s: s.sale_line_id and s.role_id.x_is_a_room_offer
            ).sale_line_id
            if lines:
                self.env.add_to_compute(self.env['sale.order.line']._fields['name'], lines)
        return res

    def _x_check_room_type(self, resource_id):
        """Refuse de déplacer une chambre réservée vers une chambre d'un autre
        type : la nouvelle ressource doit accepter le rôle du créneau
        (role_ids ; default_role_id est réservé au groupe RH)."""
        resource = self.env['resource.resource'].browse(resource_id)
        if not resource or not resource.role_ids:
            return
        for slot in self.filtered(lambda s: s.role_id.x_is_a_room_offer):
            if slot.role_id not in resource.role_ids:
                raise UserError(
                    "Chambre %s : c'est une « %s », la réservation porte sur une « %s ».\n"
                    "Pour changer de type de chambre, utilisez l'action "
                    "« Changer de chambre » depuis la réservation." % (
                        resource.name,
                        ", ".join(resource.role_ids.mapped('name')),
                        slot.role_id.name,
                    )
                )

    def _x_sync_room_line_dates(self, start_changed, end_changed):
        """Reporte les dates d'une barre de chambre sur sa ligne de commande,
        via _adjust_room_stay_date (même logique que le check-in/out : chambre
        séparée si la ligne en regroupe plusieurs, prix recalculé).

        Les nouvelles dates sont mémorisées avant le premier ajustement : la
        resynchronisation ligne → créneau qu'il déclenche remet temporairement
        l'ancienne fin sur le créneau, corrigée par le second ajustement.
        """
        slots = self.filtered(
            lambda s: s.sale_line_id
            and s.role_id.x_is_a_room_offer
            and s.sale_line_id.order_id.state != 'cancel'
        )
        for slot in slots:
            new_start, new_end = slot.start_datetime, slot.end_datetime
            line = slot.sale_line_id
            if start_changed and line.x_room_start_date != new_start:
                line = line._adjust_room_stay_date(slot, 'start', new_start)
            if end_changed and line.x_room_return_date != new_end:
                line._adjust_room_stay_date(slot, 'end', new_end)

    @api.depends('role_id', 'sale_line_id')
    def _compute_display_name(self):
        super()._compute_display_name()
        # Chambre vendue : le nom de la ligne de commande contient déjà le
        # produit ("S00137 - Chambre Double (Petit déjeuner inclus)"), le rôle
        # "Chambre Double" ferait doublon. Un devis (sans commande) garde son
        # rôle, seule indication de la chambre sur sa pastille.
        for slot in self:
            role_name = slot.role_id.display_name
            if not (slot.sale_line_id and role_name):
                continue
            parts = slot.display_name.split(' - ')
            if role_name in parts:
                parts.remove(role_name)
                slot.display_name = ' - '.join(parts)

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