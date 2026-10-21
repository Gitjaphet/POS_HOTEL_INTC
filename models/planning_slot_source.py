from odoo import fields, models


class PlanningSlot(models.Model):
    """Source de la réservation, exposée au planning hôtel pour l'étiquette
    de chaque barre (champs related non stockés : rien en base)."""
    _inherit = "planning.slot"

    x_booking_source_id = fields.Many2one(
        related="sale_line_id.order_id.source_id", string="Source de réservation",
    )
    x_booking_source_code = fields.Char(related="sale_line_id.order_id.source_id.x_booking_code")
    x_booking_source_color = fields.Char(related="sale_line_id.order_id.source_id.x_booking_color")
