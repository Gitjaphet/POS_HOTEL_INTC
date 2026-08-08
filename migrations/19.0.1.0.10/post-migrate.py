import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Force le recompute initial de x_invoice_is_active sur toutes les
    charges existantes en base, puisque ce nouveau champ stocké est vide
    (False) par défaut tant qu'aucune modification ne déclenche son
    @api.depends naturellement (x_invoice_id.state / x_invoice_id.payment_state)."""
    env = None
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    charges = env['pos.hotel.folio.charge'].search([('x_invoice_id', '!=', False)])
    _logger.info(
        "POS_HOTEL_INTC 19.0.1.0.10 : recompute x_invoice_is_active sur %d charges facturées",
        len(charges),
    )
    charges._compute_invoice_is_active()