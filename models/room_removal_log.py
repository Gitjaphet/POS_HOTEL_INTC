from odoo import fields, models


class PosHotelRoomRemovalLog(models.Model):
    _name = "pos.hotel.room.removal.log"
    _description = "Historique des chambres d'un séjour (retraits et changements)"
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
        string="Date",
        required=True,
        default=fields.Datetime.now,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Par",
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
    # Changements de chambre (action « Changer de chambre ») : même journal
    # que les retraits, pour un historique unique par séjour. Défaut
    # « Retrait » : les entrées existantes restent des retraits.
    event_type = fields.Selection(
        [("removal", "Retrait"), ("change", "Changement")],
        string="Événement",
        required=True,
        default="removal",
    )
    new_resource_id = fields.Many2one(
        "resource.resource",
        string="Nouvelle chambre",
        ondelete="set null",
    )
    new_resource_name = fields.Char(
        string="Nom de la nouvelle chambre",
    )
    pricing_mode = fields.Selection(
        [
            ("same_type", "Même type"),
            ("upgrade", "Surclassement gratuit"),
            ("reprice", "Nouveau tarif"),
        ],
        string="Tarif",
    )
