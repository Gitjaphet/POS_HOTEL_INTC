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

    @api.model
    def _create_from_pos_order_line(self, pos_order, sale_order, line, payment_status):
        return self.create({
            "name": line.full_product_name or line.product_id.display_name,
            "sale_order_id": sale_order.id,
            "partner_id": pos_order.partner_id.id,
            "pos_order_id": pos_order.id,
            "amount": line.price_subtotal_incl,
            "payment_status": payment_status,
        })