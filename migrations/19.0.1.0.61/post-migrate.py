import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Comptes de l'hôtel en réglages de la société (24/10/2026) : remplit
    les quatre réglages des bases existantes avec les comptes déjà utilisés
    (411200, 411300, 707200, 707300), pour qu'ils soient visibles dans
    Paramètres > Hôtel dès la mise à jour."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env["res.company"].search([]):
        company._x_hotel_fill_accounts()
        _logger.info(
            "POS_HOTEL_INTC : comptes de l'hôtel de %s : %s",
            company.name,
            [
                company.x_hotel_extras_receivable_account_id.code,
                company.x_hotel_services_receivable_account_id.code,
                company.x_hotel_extras_income_account_id.code,
                company.x_hotel_services_income_account_id.code,
            ],
        )
