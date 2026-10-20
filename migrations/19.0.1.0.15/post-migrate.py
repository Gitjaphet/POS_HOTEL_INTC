import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Statut d'occupation des chambres piloté par POS_HOTEL_INTC.

    Désactive les automatisations booking_engine qui écrivaient x_occupancy
    selon l'état global de la commande, puis recalcule toutes les chambres
    depuis les créneaux. Le post_init_hook fait la même chose à
    l'installation, mais ne se relance jamais lors d'un simple upgrade.
    """
    from odoo import api, SUPERUSER_ID
    from odoo.addons.POS_HOTEL_INTC.hooks import (
        _disable_room_occupancy_automation,
        _sync_all_room_occupancy,
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    _disable_room_occupancy_automation(env)
    _sync_all_room_occupancy(env)
    _logger.info("POS_HOTEL_INTC 19.0.1.0.15 : statut d'occupation des chambres resynchronisé.")
