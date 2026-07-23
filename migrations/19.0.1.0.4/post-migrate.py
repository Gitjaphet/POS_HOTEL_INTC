import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Charge = env["pos.hotel.folio.charge"]

    # On repart de zéro sur les liens original_charge_id posés par la
    # migration précédente (19.0.1.0.3), qui pouvait mal les assigner
    # quand due/payé POS partageaient le même pos_order_line_id.
    refund_charges = Charge.search([("is_refund", "=", True)])
    refund_charges.write({"original_charge_id": False})

    for charge in refund_charges:
        line = charge.pos_order_line_id
        if not line or not line.refunded_orderline_id:
            _logger.warning(
                "Remboursement %s (id=%s) : pas de refunded_orderline_id, lien d'origine non établi.",
                charge.name, charge.id,
            )
            continue

        # On matche à la fois sur la ligne POS d'origine ET sur le statut de
        # paiement, car une même ligne POS peut avoir généré deux charges
        # (due + payé POS) en cas de split payment.
        original = Charge.search([
            ("pos_order_line_id", "=", line.refunded_orderline_id.id),
            ("is_refund", "=", False),
            ("payment_status", "=", charge.payment_status),
        ], limit=1)
        if original:
            charge.original_charge_id = original.id
        else:
            _logger.warning(
                "Remboursement %s (id=%s) : aucune charge d'origine trouvée pour la ligne %s (statut %s).",
                charge.name, charge.id, line.id, charge.payment_status,
            )