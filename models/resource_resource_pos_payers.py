from odoo import api, models


class ResourceResource(models.Model):
    """Liste de la fenêtre « Transfert Chambre » du POS : une ligne par
    PERSONNE qui peut payer, pas par chambre (23/10/2026).

    Le barman sait qui consomme ; il choisit la personne, qui devient le
    client du ticket, donc le payeur de la consommation (pos_order ->
    folio_charge.partner_id). Pour chaque chambre arrivée
    (_x_current_checked_in_slot, même règle qu'avant) :
    - chaque occupant enregistré (onglet Occupants), le principal en tête ;
    - aucun occupant enregistré : le client de la réservation ;
    - réservation d'agence avec pension prise en charge : une ligne pour
      l'agence (repas compris dans le contrat).
    Dans une ligne de chambre groupée, chaque occupant n'apparaît qu'une fois.
    """
    _inherit = "resource.resource"

    @api.model
    def x_hotel_pos_payers(self):
        rows = []
        seen = set()
        agency_orders = set()
        rooms = self.sudo().search(self._get_room_resource_domain())
        for room in rooms:
            slot = room._x_current_checked_in_slot()
            if not slot:
                continue
            line = slot.sale_line_id
            order = line.order_id
            agency = order.x_agency_partner_id
            guests = line.x_stay_guest_ids.sorted(
                lambda g: (not g.is_main, g.is_child, g.sequence, g.id)
            )
            partners = guests.partner_id or order.partner_id
            for partner in partners:
                if (line.id, partner.id) in seen:
                    continue
                seen.add((line.id, partner.id))
                rows.append({
                    "room_id": room.id,
                    "room_name": room.name,
                    "partner_id": partner.id,
                    "partner_name": partner.name,
                    "agency_name": agency.name or "",
                    "is_agency": False,
                    "order_name": order.name,
                })
            if agency and order.x_agency_pays_board and order.id not in agency_orders:
                agency_orders.add(order.id)
                rows.append({
                    "room_id": room.id,
                    "room_name": room.name,
                    "partner_id": agency.id,
                    "partner_name": agency.name,
                    "agency_name": agency.name,
                    "is_agency": True,
                    "order_name": order.name,
                })
        return rows
