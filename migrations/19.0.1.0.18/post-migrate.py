import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Tâche en cours = ménage le plus récent ; en-têtes de la liste des
    chambres traduits (overwrite des traductions)."""
    from odoo import api, SUPERUSER_ID
    from odoo.addons.POS_HOTEL_INTC.hooks import _apply_hotel_labels, _fix_ongoing_task_compute

    env = api.Environment(cr, SUPERUSER_ID, {})
    _fix_ongoing_task_compute(env)
    _apply_hotel_labels(env)
    _logger.info("POS_HOTEL_INTC 19.0.1.0.18 : tâche en cours corrigée, libellés appliqués.")
