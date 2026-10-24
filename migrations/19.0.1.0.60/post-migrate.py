import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Anciens tickets payés en « Transfert Chambre » avec un dû restaurant
    (customer_due_total de pos_settle_due) calculé AVANT la neutralisation de
    _compute_customer_due_total : ils apparaissaient dans « Régler les
    commandes » alors qu'ils se règlent à la réception (note de séjour),
    d'où un risque de double paiement. Remise à 0 de ce dû, seulement pour
    les tickets sans paiement « Compte client » ordinaire ; les tickets
    mixtes sont signalés, pas modifiés. Aucune écriture comptable touchée.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["pos.order"].search([("customer_due_total", ">", 0)])
    room = orders.filtered(
        lambda o: any(p.payment_method_id.is_room_charge for p in o.payment_ids)
    )
    mixed = room.filtered(
        lambda o: any(
            p.amount > 0
            and p.payment_method_id.type == "pay_later"
            and not p.payment_method_id.is_room_charge
            for p in o.payment_ids
        )
    )
    pure = room - mixed
    pure.write({"customer_due_total": 0, "init_customer_due_total": 0})
    _logger.info(
        "POS_HOTEL_INTC : dû restaurant remis à 0 sur %s ticket(s) payé(s) en Transfert Chambre (%s)",
        len(pure), ", ".join(pure.mapped("pos_reference")),
    )
    if mixed:
        _logger.warning(
            "POS_HOTEL_INTC : %s ticket(s) mixte(s) Transfert Chambre + Compte client à vérifier à la main : %s",
            len(mixed), ", ".join(mixed.mapped("pos_reference")),
        )
