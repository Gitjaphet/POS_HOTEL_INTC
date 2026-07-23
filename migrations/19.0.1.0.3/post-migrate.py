import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    Charge = env["pos.hotel.folio.charge"]

    # Étape 1 : retrouver pos_order_line_id sur les charges qui ne l'ont pas
    charges_without_line = Charge.search([("pos_order_line_id", "=", False)])
    for charge in charges_without_line:
        order = charge.pos_order_id
        if not order:
            _logger.warning(
                "Folio charge %s (id=%s) sans pos_order_id, impossible de relier.",
                charge.name, charge.id,
            )
            continue

        candidates = order.lines.filtered(
            lambda l: (l.full_product_name or l.product_id.display_name) == charge.name
        )
        if not candidates:
            _logger.warning(
                "Folio charge %s (id=%s) : aucune ligne POS correspondante trouvée sur la commande %s.",
                charge.name, charge.id, order.name,
            )
            continue

        if len(candidates) == 1:
            line = candidates[0]
        else:
            # Plusieurs lignes du même produit sur la commande (ex. split payment) :
            # on choisit celle dont le total des charges déjà assignées + cette charge
            # correspond au sous-total de la ligne.
            line = False
            for candidate in candidates:
                already_assigned = Charge.search([("pos_order_line_id", "=", candidate.id)])
                assigned_total = sum(already_assigned.mapped("amount"))
                if abs(assigned_total + charge.amount - candidate.price_subtotal_incl) < 0.01:
                    line = candidate
                    break
            if not line:
                line = candidates[0]
                _logger.warning(
                    "Folio charge %s (id=%s) : plusieurs lignes candidates, correspondance par "
                    "montant impossible, assignation par défaut à la première ligne trouvée.",
                    charge.name, charge.id,
                )

        charge.pos_order_line_id = line.id

    # Étape 2 : marquer is_refund sur les charges de remboursement déjà créées
    refund_charges = Charge.search([("name", "like", "Remboursement — %"), ("is_refund", "=", False)])
    refund_charges.write({"is_refund": True})

    # Étape 3 : relier chaque remboursement à sa charge d'origine via refunded_orderline_id
    for charge in refund_charges:
        line = charge.pos_order_line_id
        if not line or not line.refunded_orderline_id:
            _logger.warning(
                "Remboursement %s (id=%s) : pas de refunded_orderline_id, lien d'origine non établi.",
                charge.name, charge.id,
            )
            continue

        original = Charge.search([
            ("pos_order_line_id", "=", line.refunded_orderline_id.id),
            ("is_refund", "=", False),
        ], limit=1)
        if original:
            charge.original_charge_id = original.id
        else:
            _logger.warning(
                "Remboursement %s (id=%s) : aucune charge d'origine trouvée pour la ligne %s.",
                charge.name, charge.id, line.id,
            )