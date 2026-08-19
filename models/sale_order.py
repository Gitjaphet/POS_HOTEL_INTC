from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

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