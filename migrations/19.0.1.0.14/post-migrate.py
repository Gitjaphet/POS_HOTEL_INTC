import logging

_logger = logging.getLogger(__name__)

BOOKING_SOURCES = (
    'utm_source_booking_com',
    'utm_source_website',
    'utm_source_direct',
    'utm_source_walk_in',
    'utm_source_agency',
)


def migrate(cr, version):
    """Coche x_is_booking_source sur les sources de réservation de départ.

    Elles ont été créées en noupdate (data/booking_sources.xml) avant l'ajout
    du champ : le fichier de données ne les retouche plus lors des mises à
    jour. Sans cette coche, le filtre du champ « Source de réservation » les
    masquerait toutes.
    """
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    marked = 0
    for xmlid in BOOKING_SOURCES:
        source = env.ref(f'POS_HOTEL_INTC.{xmlid}', raise_if_not_found=False)
        if source:
            source.x_is_booking_source = True
            marked += 1
    _logger.info("POS_HOTEL_INTC 19.0.1.0.14 : %s source(s) de réservation cochée(s).", marked)
