from odoo import api, fields, models


class PosHotelFolioCharge(models.Model):
    _name = "pos.hotel.folio.charge"
    _description = "Consommation POS transférée sur un folio de séjour"
    _order = "date desc"

    name = fields.Char(
        string="Description",
        required=True,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Folio",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Occupant",
        help="Client en chambre ayant consommé.",
    )
    pos_order_id = fields.Many2one(
        "pos.order",
        string="Commande POS",
        ondelete="restrict",
        help="Commande POS d'origine, pour traçabilité.",
    )
    pos_order_line_id = fields.Many2one(
        "pos.order.line",
        string="Ligne de commande POS",
        ondelete="restrict",
        index=True,
        help="Ligne POS d'origine ayant généré cette ligne folio, pour retrouver ce qui doit être compensé en cas de remboursement.",
    )
    amount = fields.Monetary(
        string="Montant",
        required=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        store=True,
    )
    date = fields.Datetime(
        string="Date",
        required=True,
        default=fields.Datetime.now,
    )
    payment_status = fields.Selection(
        [
            ("paid_pos", "Payé au POS"),
            ("due", "Dû"),
            ("settled", "Réglé"),
        ],
        string="Statut",
        required=True,
        default="due",
    )
    company_id = fields.Many2one(
        related="sale_order_id.company_id",
        store=True,
    )
    pos_config_id = fields.Many2one(
        "pos.config",
        related="pos_order_id.session_id.config_id",
        string="Point de Vente",
        store=True,
        readonly=True,
    )
    is_refund = fields.Boolean(
        string="Est un remboursement",
        default=False,
        help="Coché automatiquement pour les lignes créées en compensation d'un remboursement POS.",
    )
    original_charge_id = fields.Many2one(
        "pos.hotel.folio.charge",
        string="Charge d'origine",
        ondelete="restrict",
        index=True,
        help="Si cette ligne est un remboursement, référence la ligne folio qu'elle compense.",
    )
    refund_charge_ids = fields.One2many(
        "pos.hotel.folio.charge",
        "original_charge_id",
        string="Remboursements liés",
    )
    amount_refunded = fields.Monetary(
        string="Montant remboursé",
        compute="_compute_amount_refunded",
        store=True,
        help="Somme des remboursements liés à cette ligne (valeur positive).",
    )
    amount_net = fields.Monetary(
        string="Montant net",
        compute="_compute_amount_refunded",
        store=True,
        help="Montant restant après déduction des remboursements liés.",
    )
    refund_status = fields.Selection(
        [
            ("none", "Aucun"),
            ("partial", "Partiel"),
            ("full", "Total"),
        ],
        string="Statut remboursement",
        compute="_compute_amount_refunded",
        store=True,
    )

    @api.depends("amount", "refund_charge_ids.amount")
    def _compute_amount_refunded(self):
        for charge in self:
            refunded = -sum(charge.refund_charge_ids.mapped("amount"))
            charge.amount_refunded = refunded
            charge.amount_net = charge.amount - refunded
            if charge.currency_id.is_zero(refunded):
                charge.refund_status = "none"
            elif charge.currency_id.is_zero(charge.amount_net):
                charge.refund_status = "full"
            else:
                charge.refund_status = "partial"

    @api.model
    def _create_from_pos_order_line(self, pos_order, sale_order, line, payment_status, amount=None):
        return self.create({
            "name": line.full_product_name or line.product_id.display_name,
            "sale_order_id": sale_order.id,
            "partner_id": pos_order.partner_id.id,
            "pos_order_id": pos_order.id,
            "pos_order_line_id": line.id,
            "amount": amount if amount is not None else line.price_subtotal_incl,
            "payment_status": payment_status,
        })

    @api.model
    def _create_refund_from_charge(self, original_charge, pos_order, refund_line, ratio):
        return self.create({
            "name": f"Remboursement — {original_charge.name}",
            "sale_order_id": original_charge.sale_order_id.id,
            "partner_id": original_charge.partner_id.id,
            "pos_order_id": pos_order.id,
            "pos_order_line_id": refund_line.id,
            "amount": -original_charge.amount * ratio,
            "payment_status": original_charge.payment_status,
            "is_refund": True,
            "original_charge_id": original_charge.id,
        })