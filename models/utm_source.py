from odoo import fields, models


class UtmSource(models.Model):
    _inherit = "utm.source"

    x_booking_code = fields.Char(
        string="Code planning", size=4,
        help="Étiquette courte affichée sur les barres du planning (B, E, W...).",
    )
    x_booking_color = fields.Char(
        string="Couleur planning",
        help="Couleur de l'étiquette sur les barres du planning (ex. #003580).",
    )
