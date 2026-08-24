import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Complète la désactivation de l'automation forçant les horaires :
    couvre aussi 'sale.order' (règle #4 "Définir les heures de début/fin de
    location à la création"), symétrique de celle sur planning.slot déjà
    traitée en 19.0.1.0.12. Même cause racine, même conflit avec
    POS_HOTEL_INTC (voir hooks.py::_disable_room_hours_automation)."""
    from odoo import api, SUPERUSER_ID
    from odoo.addons.POS_HOTEL_INTC.hooks import _disable_room_hours_automation

    env = api.Environment(cr, SUPERUSER_ID, {})
    _disable_room_hours_automation(env)
    _logger.info("POS_HOTEL_INTC 19.0.1.0.13 : automation sale.order également désactivée (si présente).")