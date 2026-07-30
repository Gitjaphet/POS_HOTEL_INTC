from odoo import api, fields, models


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
        domain=[("is_refund", "=", False)],
    )
    x_folio_charge_refund_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "sale_order_id",
        string="Remboursements",
        domain=[("is_refund", "=", True)],
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

    @api.depends(
        "x_folio_charge_normal_ids.amount_net",
        "x_folio_charge_normal_ids.payment_status",
    )
    def _compute_folio_totals(self):
        for order in self:
            charges = order.x_folio_charge_normal_ids
            order.x_folio_total_paid = sum(
                charges.filtered(lambda c: c.payment_status in ("paid_pos", "settled")).mapped("amount_net")
            )
            order.x_folio_total_due = sum(
                charges.filtered(lambda c: c.payment_status == "due").mapped("amount_net")
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

    def _action_cancel(self):
        res = super()._action_cancel()
        self.order_line.planning_slot_ids.unlink()
        self.order_line._notify_room_occupancy_change()
        return res