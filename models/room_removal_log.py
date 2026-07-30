from odoo import fields, models


class PosHotelRoomRemovalLog(models.Model):
    _name = "pos.hotel.room.removal.log"
    _description = "Historique des chambres retirées d'un séjour"
    _order = "date desc"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Folio",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne",
        ondelete="set null",
        index=True,
    )
    resource_id = fields.Many2one(
        "resource.resource",
        string="Chambre",
        ondelete="set null",
    )
    resource_name = fields.Char(
        string="Nom de la chambre",
        required=True,
    )
    date = fields.Datetime(
        string="Date du retrait",
        required=True,
        default=fields.Datetime.now,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Retiré par",
        required=True,
        default=lambda self: self.env.user,
    )
    reason = fields.Text(
        string="Motif",
        required=True,
    )
    cancel_due_debt = fields.Boolean(
        string="Dette annulée",
    )
    due_amount_at_removal = fields.Monetary(
        string="Montant dû au moment du retrait",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
    )