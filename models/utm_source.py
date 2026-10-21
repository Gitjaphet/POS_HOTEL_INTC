from odoo import fields, models


class UtmSource(models.Model):
    _inherit = 'utm.source'

    # Canal de réservation hôtel (Booking.com, Site web, Walk-in…) : seules
    # ces sources sont proposées dans « Source de réservation ». Les sources
    # des autres modules (marketing, recrutement) restent intactes.
    x_is_booking_source = fields.Boolean(string="Source de réservation hôtel")

    # Étiquette de la source sur les barres du planning hôtel (réglable dans
    # Réservation(s) > Configuration > Sources de réservation).
    x_booking_code = fields.Char(
        string="Code planning", size=4,
        help="Étiquette courte affichée sur les barres du planning (B, E, W...).",
    )
    x_booking_color = fields.Char(
        string="Couleur planning",
        help="Couleur de l'étiquette sur les barres du planning (ex. #003580).",
    )
