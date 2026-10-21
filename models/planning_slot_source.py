from odoo import api, fields, models


class PlanningSlot(models.Model):
    """Source de la réservation, exposée au planning hôtel pour l'étiquette
    de chaque barre (champs related non stockés : rien en base)."""
    _inherit = "planning.slot"

    x_booking_source_id = fields.Many2one(
        related="sale_line_id.order_id.source_id", string="Source de réservation",
    )
    x_booking_source_code = fields.Char(related="sale_line_id.order_id.source_id.x_booking_code")
    x_booking_source_color = fields.Char(related="sale_line_id.order_id.source_id.x_booking_color")

    @api.model
    def get_hotel_planning_stats(self, period_start=None, period_stop=None, reference_date=None):
        """Compteurs du tableau de bord + légende des sources de réservation
        (code, nom, couleur), construite depuis les réglages : la légende suit
        automatiquement toute source ajoutée ou modifiée par l'hôtel."""
        res = super().get_hotel_planning_stats(
            period_start=period_start, period_stop=period_stop, reference_date=reference_date,
        )
        sources = self.env["utm.source"].search([
            ("x_is_booking_source", "=", True),
            ("x_booking_code", "!=", False),
        ], order="name")
        res["sources"] = [
            {"code": s.x_booking_code, "name": s.name, "color": s.x_booking_color or "#6C757D"}
            for s in sources
        ]
        return res
