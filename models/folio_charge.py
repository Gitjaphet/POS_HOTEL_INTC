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
        })