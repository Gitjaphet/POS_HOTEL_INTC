import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Crée les comptes 411300 (Créances Service Chambre) et 707300 (Ventes
    services chambre) sur toutes les sociétés, comme le fait post_init_hook
    à l'installation initiale — mécanisme qui ne se relance jamais tout seul
    à un simple upgrade de module."""
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    companies = env['res.company'].search([])
    for company in companies:
        env['pos.payment.method']._ensure_service_charge_account(company)
        env['pos.payment.method']._ensure_service_income_account(company)
    _logger.info(
        "POS_HOTEL_INTC 19.0.1.0.11 : comptes 411300/707300 créés/vérifiés sur %d société(s)",
        len(companies),
    )