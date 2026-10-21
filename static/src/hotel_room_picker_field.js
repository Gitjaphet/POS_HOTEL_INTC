import { registry } from "@web/core/registry";
import {
    Many2OneField,
    buildM2OFieldDescription,
} from "@web/views/fields/many2one/many2one_field";

/**
 * Colonne « Chambre » des réservations : une seule colonne pour deux usages.
 * - ligne qui a déjà ses chambres (créneaux) : texte « 201, 202 » ;
 * - nouvelle ligne : le menu Many2one NATIF d'Odoo (gabarit web.Many2OneField,
 *   recherche, domaine des chambres libres, options) — rien n'est réécrit.
 */
export class HotelRoomPickerField extends Many2OneField {
    static template = "POS_HOTEL_INTC.HotelRoomPickerField";

    get hotelRoomNames() {
        return this.props.record.data.x_room_resource_names || "";
    }
}

registry.category("fields").add("hotel_room_picker", {
    ...buildM2OFieldDescription(HotelRoomPickerField),
    displayName: "Chambre (hôtel)",
});
