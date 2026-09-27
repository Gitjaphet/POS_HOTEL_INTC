from odoo import fields, models


class UtmSource(models.Model):
    _inherit = 'utm.source'

    # Canal de réservation hôtel (Booking.com, Site web, Walk-in…) : seules
    # ces sources sont proposées dans « Source de réservation ». Les sources
    # des autres modules (marketing, recrutement) restent intactes.
    x_is_booking_source = fields.Boolean(string="Source de réservation hôtel")
