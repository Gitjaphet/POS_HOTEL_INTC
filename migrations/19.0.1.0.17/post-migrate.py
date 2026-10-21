import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Noms hôteliers des menus : force la traduction française de notre
    fr.po par-dessus celle de booking_engine (non écrasée à l'upgrade)."""
    from odoo import api, SUPERUSER_ID
    from odoo.addons.POS_HOTEL_INTC.hooks import _apply_hotel_labels

    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_hotel_labels(env)
    _logger.info("POS_HOTEL_INTC 19.0.1.0.17 : noms hôteliers des menus appliqués.")
