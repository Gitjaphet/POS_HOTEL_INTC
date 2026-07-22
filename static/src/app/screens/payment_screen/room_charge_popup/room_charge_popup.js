import { Component, useState } from "@odoo/owl";
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
    }

    get occupants() {
        const rooms = this.pos.models["resource.resource"].getAll();
        const search = this.state.search.trim().toLowerCase();
        const rows = [];

        for (const room of rooms) {
            for (const partner of room.x_occupant_ids) {
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

    selectOccupant(partner) {
        this.props.getPayload(partner);
        this.props.close();
    }
}