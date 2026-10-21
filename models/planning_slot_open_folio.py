from odoo import models


class PlanningSlot(models.Model):
    """Ouverture d'une réservation depuis le planning VIA l'action
    « Réservations » (booking_engine_rooms_order_action, réglée sur la fiche
    hôtel par hooks._fix_booking_engine_order_form_view).

    Une action sans identifiant laissait l'adresse en « /sale.order/<id> » :
    au rechargement (F5), Odoo rouvrait la fiche location native (Enlèvement /
    Retour) au lieu de la fiche hôtel (21/10/2026). Avec l'action, l'adresse
    porte son identifiant et la fiche hôtel est retrouvée.
    """
    _inherit = "planning.slot"

    def _x_hotel_folio_action(self, order):
        action = self.env["ir.actions.actions"]._for_xml_id(
            "booking_engine.booking_engine_rooms_order_action"
        )
        view = self.env.ref("POS_HOTEL_INTC.sale_order_primary_view_pos_hotel_intc")
        action.update({
            "res_id": order.id,
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "current",
        })
        return action

    def action_open_hotel_folio(self):
        """Bouton « Ouvrir la fiche » du popover du planning hôtel."""
        self.ensure_one()
        order = self.sale_line_id.order_id
        if not order:
            return False
        return self._x_hotel_folio_action(order)

    def action_view_sale_order(self):
        """Bouton natif « Commande » du créneau : fiche hôtel pour une
        réservation de chambre, comportement natif sinon."""
        order = self.sale_order_id
        if len(self) == 1 and order and order.x_order_involves_room:
            return self._x_hotel_folio_action(order)
        return super().action_view_sale_order()
