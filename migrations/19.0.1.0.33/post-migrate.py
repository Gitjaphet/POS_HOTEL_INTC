import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Tâche de minuit booking_engine : ménage uniquement pour les chambres
    dont le client a fait son Arrivée (plus de ménage pour un no-show)."""
    from odoo import api, SUPERUSER_ID
    from odoo.addons.POS_HOTEL_INTC.hooks import _restrict_hk_cron_to_checked_in

    env = api.Environment(cr, SUPERUSER_ID, {})
    _restrict_hk_cron_to_checked_in(env)
    _logger.info("POS_HOTEL_INTC 19.0.1.0.33 : ménage de minuit limité aux chambres enregistrées.")
