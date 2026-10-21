import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Codes et couleurs par défaut des sources de réservation (étiquettes du
    planning) ; libellé français du menu Sources de réservation."""
    from odoo import api, SUPERUSER_ID
    from odoo.addons.POS_HOTEL_INTC.hooks import _apply_booking_source_defaults, _apply_hotel_labels

    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_booking_source_defaults(env)
    _apply_hotel_labels(env)
    _logger.info("POS_HOTEL_INTC 19.0.1.0.24 : étiquettes des sources de réservation appliquées.")
