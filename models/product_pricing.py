import math

import pytz

from odoo import models


class ProductPricing(models.Model):
    _inherit = 'product.pricing'

    def _compute_duration_vals(self, start_date, end_date):
        """Règle hôtelière (comme eZee) quand le contexte porte hotel_nights :
        une nuit = un changement de date dans le fuseau de l'hôtel, quelles
        que soient les heures d'arrivée et de départ (minimum 1).

        hour est renvoyé en multiple exact de 24 : le ceil() du prix
        (_compute_price) et le round() de l'affichage
        (_get_converted_duration_and_label) donnent le même nombre de nuits.
        Arrivée tôt / départ tardif : frais séparés, jamais une nuit auto.
        """
        vals = super()._compute_duration_vals(start_date, end_date)
        if not self.env.context.get('hotel_nights'):
            return vals
        tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')

        def local_date(dt):
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            return dt.astimezone(tz).date()

        nights = max(1, (local_date(end_date) - local_date(start_date)).days)
        vals['hour'] = nights * 24
        vals['day'] = nights
        vals['week'] = math.ceil(nights / 7)
        return vals
