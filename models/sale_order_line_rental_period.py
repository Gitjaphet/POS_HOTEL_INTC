from odoo import models


class SaleOrderLine(models.Model):
    """Période de la réservation (rental_start_date / rental_return_date)
    toujours calculée sur les seules chambres ACTIVES (quantité > 0).

    Le write() de sale_order_line.py ne recalcule la période que sur un
    changement de dates ; une chambre retirée (⊖, quantité 0) laissait sa
    date de fin sur la réservation (S00152 : 401 retirée, fin restée au 24,
    21/10/2026) — badge « Retour tardif » et compteurs décalés d'un jour.
    """
    _inherit = "sale.order.line"

    def write(self, vals):
        res = super().write(vals)
        if "product_uom_qty" in vals and not self.env.context.get("x_syncing_room_dates"):
            self.filtered("x_is_a_room_offer")._x_update_order_rental_period()
        return res

    def _x_update_order_rental_period(self):
        """Min/max des dates des chambres actives de chaque réservation.
        Même écriture que sale_order_line.write() (slots_rescheduled=True :
        les créneaux, déjà justes, ne sont pas repoussés). Aucune chambre
        active : la période n'est pas touchée."""
        for order in self.order_id:
            active = order.order_line.filtered(
                lambda l: l.x_is_a_room_offer
                and l.product_uom_qty > 0
                and l.x_room_start_date and l.x_room_return_date
            )
            if not active:
                continue
            start = min(active.mapped("x_room_start_date"))
            stop = max(active.mapped("x_room_return_date"))
            if order.rental_start_date != start or order.rental_return_date != stop:
                order.with_context(slots_rescheduled=True).write({
                    "rental_start_date": start,
                    "rental_return_date": stop,
                })
