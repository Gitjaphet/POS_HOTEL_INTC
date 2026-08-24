import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Désactive l'action d'automatisation Studio "Ajuster les horaires des
    créneaux" (base.automation sur planning.slot), comme le fait
    post_init_hook à l'installation initiale — mécanisme qui ne se relance
    jamais tout seul à un simple upgrade de module.

    CONFLIT AVEC POS_HOTEL_INTC : cette règle forçait systématiquement
    start_datetime/end_datetime des planning.slot à pickup_time/return_time
    (récurrence "Nights"), en écrasant toute heure de début/fin de séjour
    personnalisée saisie via x_room_start_date/x_room_return_date. Cause
    racine confirmée du bug de désynchro Planning <-> commande
    (investigation du 22/08/2026)."""
    from odoo import api, SUPERUSER_ID
    from odoo.addons.POS_HOTEL_INTC.hooks import _disable_room_hours_automation

    env = api.Environment(cr, SUPERUSER_ID, {})
    _disable_room_hours_automation(env)
    _logger.info(
        "POS_HOTEL_INTC 19.0.1.0.12 : automation 'Ajuster les horaires des "
        "créneaux' désactivée (si présente)."
    )