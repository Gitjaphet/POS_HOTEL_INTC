import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

export class RoomChargePopup extends Component {
    static template = "pos_hotel_intc.RoomChargePopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
    };

    setup() {
        this.pos = usePos();
        this.state = useState({ search: "" });
        // Liste toujours à jour au moment du choix : les chambres sont relues
        // sur le serveur à chaque ouverture (x_current_partner_id y est
        // recalculé), sans dépendre du signal ROOM_OCCUPANCY_UPDATED ni de la
        // copie locale du POS. Hors connexion : dernière liste connue.
        onWillStart(() => this.refreshRooms());
    }

    async refreshRooms() {
        const roomIds = this.pos.models["resource.resource"].getAll().map((room) => room.id);
        if (!roomIds.length) {
            return;
        }
        try {
            await this.pos.data.read(
                "resource.resource",
                roomIds,
                ["id", "name", "x_occupant_ids", "x_current_partner_id"]
            );
        } catch {
            // Serveur injoignable : on garde la liste déjà chargée.
        }
    }

    get occupants() {
        const rooms = this.pos.models["resource.resource"].getAll();
        const search = this.state.search.trim().toLowerCase();
        const rows = [];

        for (const room of rooms) {
            const partner = room.x_current_partner_id;
            if (partner) {
                rows.push({ room, partner });
            }
        }

        if (!search) {
            return rows;
        }
        return rows.filter(
            ({ room, partner }) =>
                room.name.toLowerCase().includes(search) ||
                partner.name.toLowerCase().includes(search)
        );
    }

    selectOccupant(room, partner) {
        this.props.getPayload({ partner, room });
        this.props.close();
    }
}
