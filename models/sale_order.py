from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x_stay_guest_ids = fields.One2many(
        "pos.hotel.stay.guest", "order_id", string="Occupants",
    )

    x_folio_charge_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Transferts POS",
    )
    x_folio_charge_normal_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Consommations POS",
        domain=[("is_refund", "=", False), ("is_service", "=", False)],
    )
    x_folio_charge_service_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Services",
        domain=[("is_refund", "=", False), ("is_service", "=", True)],
    )
    x_folio_charge_refund_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Remboursements",
        domain=[("is_refund", "=", True), ("is_service", "=", False)],
    )
    x_folio_charge_refund_service_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Remboursements Service",
        domain=[("is_refund", "=", True), ("is_service", "=", True)],
    )
    x_room_removal_log_ids = fields.One2many(
        "pos.hotel.room.removal.log",
        "sale_order_id",
        string="Historique des chambres retirées",
    )
    x_folio_total_paid = fields.Monetary(
        string="Total Extra Payé",
        compute="_compute_folio_totals",
        help="Somme des consommations déjà payées, au POS ou réglées ensuite par le réceptionniste.",
    )
    x_folio_total_due = fields.Monetary(
        string="Total Extra Dû",
        compute="_compute_folio_totals",
        help="Somme des consommations encore dues au réceptionniste.",
    )
    x_folio_total_paid_service = fields.Monetary(
        string="Total Service Payé",
        compute="_compute_folio_totals",
        help="Somme des services déjà payés, réglés par le réceptionniste.",
    )
    x_folio_total_due_service = fields.Monetary(
        string="Total Service Dû",
        compute="_compute_folio_totals",
        help="Somme des services encore dus au réceptionniste.",
    )
    x_folio_period_start = fields.Datetime(
        string="Début période Folio",
        compute="_compute_folio_period",
        store=True,
        help="Date de début la plus ancienne parmi tous les planning.slot des chambres du folio.",
    )
    x_folio_period_end = fields.Datetime(
        string="Fin période Folio",
        compute="_compute_folio_period",
        store=True,
        help="Date de fin la plus tardive parmi tous les planning.slot des chambres du folio.",
    )
    x_folio_is_multi_room = fields.Boolean(
        string="Folio multi-chambres",
        compute="_compute_folio_period",
        store=True,
        help="Vrai si le folio contient au moins 2 chambres avec des périodes de séjour distinctes.",
    )
    x_room_stay_slot_ids = fields.One2many(
        "planning.slot",
        string="Séjours (chambres)",
        compute="_compute_room_stay_slot_ids",
        help="Tous les planning.slot des chambres de ce folio, tous produits "
             "confondus, pour le suivi check-in/check-out par chambre précise.",
    )

    # Totaux d'occupation de la réservation (somme des chambres), stockés pour
    # les filtres, regroupements et rapports (petit déjeuner, statistiques).
    x_adults_total = fields.Integer(
        string="Adultes", compute='_compute_x_occupancy_totals', store=True,
    )
    x_children_total = fields.Integer(
        string="Enfants", compute='_compute_x_occupancy_totals', store=True,
    )

    @api.depends('order_line.x_adults', 'order_line.x_children')
    def _compute_x_occupancy_totals(self):
        for order in self:
            rooms = order.order_line.filtered('x_is_a_room_offer')
            order.x_adults_total = sum(rooms.mapped('x_adults'))
            order.x_children_total = sum(rooms.mapped('x_children'))

    x_occupancy_display = fields.Char(
        string="Occupation", compute='_compute_x_occupancy_display',
    )

    @api.depends('x_adults_total', 'x_children_total')
    def _compute_x_occupancy_display(self):
        for order in self:
            adults, children = order.x_adults_total, order.x_children_total
            order.x_occupancy_display = "%s adulte%s · %s enfant%s" % (
                adults, "s" if adults > 1 else "",
                children, "s" if children > 1 else "",
            )

    def _compute_pricelist_id(self):
        super()._compute_pricelist_id()
        # Réservation créée depuis le planning hôtel avec une liste de prix
        # choisie : elle prime sur celle du client, sinon le choix du client
        # la remplacerait (et le prix des lignes ne serait pas recalculé).
        locked_id = self.env.context.get('hotel_locked_pricelist_id')
        if locked_id:
            for order in self.filtered(lambda o: o.state in ('draft', 'sent')):
                order.pricelist_id = locked_id

    @api.depends(
        "order_line.planning_slot_ids.start_datetime",
        "order_line.planning_slot_ids.end_datetime",
        "order_line.planning_slot_ids.role_id.x_is_a_room_offer",
    )
    def _compute_folio_period(self):
        for order in self:
            room_slots = order.order_line.planning_slot_ids.filtered(
                lambda s: s.role_id.x_is_a_room_offer and s.start_datetime and s.end_datetime
            )
            starts = room_slots.mapped("start_datetime")
            ends = room_slots.mapped("end_datetime")
            order.x_folio_period_start = min(starts) if starts else False
            order.x_folio_period_end = max(ends) if ends else False
            order.x_folio_is_multi_room = len(room_slots) > 1 and (
                len(set(starts)) > 1 or len(set(ends)) > 1
            )

    @api.depends("order_line.planning_slot_ids")
    def _compute_room_stay_slot_ids(self):
        for order in self:
            order.x_room_stay_slot_ids = order.order_line.planning_slot_ids

    @api.depends(
        "x_folio_charge_normal_ids.amount_net",
        "x_folio_charge_normal_ids.payment_status",
        "x_folio_charge_normal_ids.x_invoice_is_active",
        "x_folio_charge_service_ids.amount_net",
        "x_folio_charge_service_ids.payment_status",
        "x_folio_charge_service_ids.x_invoice_is_active",
    )
    def _compute_folio_totals(self):
        for order in self:
            charges = order.x_folio_charge_normal_ids
            order.x_folio_total_paid = sum(
                charges.filtered(lambda c: c.payment_status in ("paid_pos", "settled")).mapped("amount_net")
            )
            order.x_folio_total_due = sum(
                charges.filtered(
                    lambda c: c.payment_status == "due" and not c.x_invoice_is_active
                ).mapped("amount_net")
            )
            services = order.x_folio_charge_service_ids
            order.x_folio_total_paid_service = sum(
                services.filtered(lambda c: c.payment_status in ("paid_pos", "settled")).mapped("amount_net")
            )
            order.x_folio_total_due_service = sum(
                services.filtered(
                    lambda c: c.payment_status == "due" and not c.x_invoice_is_active
                ).mapped("amount_net")
            )


    def action_open_cancel_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Annuler la commande",
            "res_model": "pos.hotel.order.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sale_order_id": self.id},
        }

    def action_open_pickup(self):
        self.ensure_one()
        if (self.company_id.x_guest_registration_scope != "none"
                and not self.env.context.get("x_guest_registration_done")
                and self.order_line.filtered("x_is_a_room_offer")):
            self._x_prefill_main_guests()
            return {
                "type": "ir.actions.act_window",
                "name": "Enregistrement des occupants",
                "res_model": "sale.order",
                "res_id": self.id,
                "view_mode": "form",
                "views": [(self.env.ref(
                    "POS_HOTEL_INTC.sale_order_view_form_guest_registration").id, "form")],
                "target": "new",
            }
        slots = self.order_line.planning_slot_ids.filtered(
            lambda s: s.x_stay_status == 'pending'
        )
        if not slots:
            return super().action_open_pickup()
        return self._open_checkin_wizard('checkin', slots)

    def action_open_return(self):
        self.ensure_one()
        slots = self.order_line.planning_slot_ids.filtered(
            lambda s: s.x_stay_status == 'checked_in'
        )
        if not slots:
            return super().action_open_return()
        return self._open_checkin_wizard('checkout', slots)

    def _open_checkin_wizard(self, status, slots):
        line_vals = [(0, 0, {'planning_slot_id': slot.id}) for slot in slots]
        return {
            'type': 'ir.actions.act_window',
            'name': "Enregistrement" if status == 'checkin' else "Départ",
            'res_model': 'pos.hotel.checkin.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_status': status,
                'default_line_ids': line_vals,
            },
        }

    # --- Enregistrement des occupants à l'arrivée ---------------------
    x_guest_registration_issues = fields.Text(
        string="Enregistrement incomplet",
        compute="_compute_x_guest_registration_issues",
    )

    @api.depends(
        "company_id.x_guest_registration_scope",
        "company_id.x_guest_require_nationality",
        "company_id.x_guest_require_document",
        "company_id.x_guest_require_birth_date",
        "order_line.x_adults", "order_line.x_children",
        "x_stay_guest_ids.sale_order_line_id", "x_stay_guest_ids.partner_id",
        "x_stay_guest_ids.is_main", "x_stay_guest_ids.is_child",
        "x_stay_guest_ids.nationality_id", "x_stay_guest_ids.document_type",
        "x_stay_guest_ids.document_number", "x_stay_guest_ids.birth_date",
    )
    def _compute_x_guest_registration_issues(self):
        for order in self:
            order.x_guest_registration_issues = "\n".join(
                order._x_guest_registration_issues()
            ) or False

    def _x_guest_registration_issues(self):
        """Ce qui manque selon Paramètres > Hôtel > Enregistrement des occupants."""
        self.ensure_one()
        company = self.company_id
        scope = company.x_guest_registration_scope
        if scope == "none":
            return []
        issues = []
        for line in self.order_line.filtered("x_is_a_room_offer"):
            room = ", ".join(line.x_room_resource_ids.mapped("name")) or line.name
            # _origin : pendant la saisie, Odoo manipule des copies temporaires.
            guests = self.x_stay_guest_ids.filtered(
                lambda g: g.sale_order_line_id._origin == line._origin
            )
            adults = guests.filtered(lambda g: not g.is_child)
            children = guests - adults
            if not guests.filtered("is_main"):
                issues.append(f"Chambre {room} : aucun occupant principal.")
            if scope in ("adults", "all") and len(adults) < line.x_adults:
                issues.append(
                    f"Chambre {room} : {len(adults)} adulte(s) enregistré(s) sur {line.x_adults}."
                )
            if scope == "all" and len(children) < line.x_children:
                issues.append(
                    f"Chambre {room} : {len(children)} enfant(s) enregistré(s) sur {line.x_children}."
                )
            checked = {
                "main": guests.filtered("is_main"),
                "adults": adults,
                "all": guests,
            }[scope]
            for guest in checked:
                missing = []
                if company.x_guest_require_nationality and not guest.nationality_id:
                    missing.append("nationalité")
                if company.x_guest_require_document and not (
                    guest.document_type and guest.document_number
                ):
                    missing.append("pièce d'identité")
                if company.x_guest_require_birth_date and not guest.birth_date:
                    missing.append("date de naissance")
                if missing:
                    issues.append(
                        f"{guest.partner_id.name or 'Occupant'} ({room}) : "
                        f"{', '.join(missing)} manquant(e)."
                    )
        return issues

    def _x_prefill_main_guests(self):
        """Client de la réservation (s'il s'agit d'une personne) proposé
        d'office comme occupant principal de la première chambre qui n'en a pas."""
        partner = self.partner_id
        if not partner or partner.is_company:
            return
        for line in self.order_line.filtered("x_is_a_room_offer"):
            if line.x_stay_guest_ids.filtered("is_main"):
                continue
            existing = line.x_stay_guest_ids.filtered(lambda g: g.partner_id == partner)
            if existing:
                existing.is_main = True
            elif not self.x_stay_guest_ids.filtered(lambda g: g.partner_id == partner):
                self.env["pos.hotel.stay.guest"].create({
                    "sale_order_line_id": line.id,
                    "partner_id": partner.id,
                    "is_main": True,
                })

    def action_x_confirm_guest_registration(self):
        """Bouton « Valider l'arrivée » : contrôle, horodatage, puis
        l'assistant d'arrivée habituel."""
        self.ensure_one()
        issues = self._x_guest_registration_issues()
        if issues:
            if self.company_id.x_guest_registration_mode == "block":
                raise UserError(
                    "Arrivée impossible, enregistrement incomplet :\n- "
                    + "\n- ".join(issues)
                )
        # Note et horodatage : à la confirmation réelle de l'arrivée
        # (assistant d'arrivée), pas ici : l'utilisateur peut encore annuler.
        return self.with_context(x_guest_registration_done=True).action_open_pickup()

    def _x_on_rooms_checked_in(self, sale_lines):
        """Appelé par l'assistant d'arrivée une fois l'arrivée confirmée :
        horodate les occupants des chambres arrivées et trace un
        enregistrement incomplet (mode Avertir)."""
        self.ensure_one()
        self.x_stay_guest_ids.filtered(
            lambda g: g.sale_order_line_id in sale_lines and not g.checkin_date
        ).checkin_date = fields.Datetime.now()
        issues = self._x_guest_registration_issues()
        if issues:
            self.message_post(
                body=Markup("Arrivée avec enregistrement incomplet :<ul>%s</ul>")
                % Markup("").join(Markup("<li>%s</li>") % i for i in issues)
            )

    def action_cancel_folio_charges(self, cancel_due_debt=False,
                                     refund_settled_charges=False,
                                     refund_payment_method_line_id=False,
                                     reason=None):
        """Vérifie et traite l'ensemble des charges du folio avant annulation
        de la commande — même logique que action_remove_room, mais appliquée
        à toutes les chambres du folio en une seule fois (blocage tout ou rien).
        Doit être appelée AVANT _action_cancel(), jamais après.
        """
        self.ensure_one()
        charges = self.x_folio_charge_normal_ids + self.x_folio_charge_service_ids

        room_active_invoices = self.order_line.invoice_lines.move_id.filtered(
            lambda m: m.move_type == 'out_invoice'
            and m.state != 'cancel'
            and m.payment_state != 'reversed'
        )
        if room_active_invoices:
            invoice_names = ', '.join(
                (inv.name or "Brouillon") for inv in room_active_invoices
            )
            raise UserError(
                f"Ce folio a une ou plusieurs chambres déjà facturées "
                f"({invoice_names}). Annulez d'abord cette facture (ou établissez "
                "un avoir) avant d'annuler la commande."
            )

        invoiced_charges = charges.filtered(
            lambda c: c.x_invoice_is_active
        )
        if invoiced_charges:
            invoice_names = ', '.join(
                (inv.name or "Brouillon") for inv in invoiced_charges.mapped('x_invoice_id')
            )
            raise UserError(
                f"Ce folio a des extras déjà inclus dans une facture non annulée "
                f"({invoice_names}). Annulez d'abord cette facture (ou établissez un avoir) "
                "avant d'annuler la commande."
            )

        paid_charges = charges.filtered(
            lambda c: c.payment_status == 'paid_pos' and not c.currency_id.is_zero(c.amount_net)
        )
        if paid_charges:
            raise UserError(
                "Ce folio a des extras payés au POS non remboursés. "
                "Effectuez d'abord le remboursement via le POS avant d'annuler la commande."
            )

        settled_charges = charges.filtered(
            lambda c: c.payment_status == 'settled' and not c.currency_id.is_zero(c.amount_net)
        )
        if settled_charges and not refund_settled_charges:
            raise UserError(
                "Ce folio a des extras ou services réglés à rembourser. "
                "Cochez le remboursement dans le wizard pour continuer."
            )
        if settled_charges and refund_settled_charges:
            if not refund_payment_method_line_id:
                raise UserError(
                    "Un mode de paiement pour le remboursement est requis."
                )
            for is_service in set(settled_charges.mapped('is_service')):
                settled_charges.filtered(
                    lambda c, v=is_service: c.is_service == v
                ).action_refund_settled(refund_payment_method_line_id)

        due_charges = charges.filtered(
            lambda c: c.payment_status == 'due' and not c.x_invoice_is_active
        )
        if due_charges and cancel_due_debt:
           due_charges._transition_to_cancelled(reason=reason or "Annulation commande")

    def _action_cancel(self):
        res = super()._action_cancel()
        self.order_line.planning_slot_ids.unlink()
        self.order_line._notify_room_occupancy_change()
        return res

    def get_formview_id(self, access_uid=None):
        if self.x_order_involves_room:
            hotel_view = self.env.ref(
                'POS_HOTEL_INTC.sale_order_primary_view_pos_hotel_intc',
                raise_if_not_found=False,
            )
            if hotel_view:
                return hotel_view.id
        return super().get_formview_id(access_uid=access_uid)


    def _get_folio_payment_state(self):
        """État de paiement global du folio : 'none', 'partial' ou 'paid'.

        Source de vérité unique de la règle 💰/✅ : utilisée à la fois par
        l'icône des pastilles du planning (planning.slot._compute_display_name)
        et par les compteurs du tableau de bord. Ne jamais dupliquer cette
        logique ailleurs, sous peine de voir les deux affichages diverger.

        'partial' = un paiement existe quelque part sur le folio (acompte,
        paiement partiel de facture, extra ou service réglé) mais il reste
        quelque chose à encaisser.
        'paid' = facture(s) chambre soldée(s) ET plus aucun extra ni service dû.
        """
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda m: m.state == "posted" and m.payment_state != "reversed"
        )
        has_invoice_payment = any(
            inv.payment_state in ("partial", "paid") for inv in invoices
        )
        has_extra_payment = (
            self.x_folio_total_paid > 0 or self.x_folio_total_paid_service > 0
        )
        if not (has_invoice_payment or has_extra_payment):
            return 'none'

        room_fully_paid = bool(invoices) and all(
            inv.payment_state == "paid" for inv in invoices
        )
        nothing_due = (
            self.x_folio_total_due == 0 and self.x_folio_total_due_service == 0
        )
        return 'paid' if (room_fully_paid and nothing_due) else 'partial'