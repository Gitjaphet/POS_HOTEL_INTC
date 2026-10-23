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
        this.state = useState({ search: "", payers: null });
        // Liste relue sur le serveur à chaque ouverture : une ligne par
        // personne qui peut payer (occupants enregistrés, agence si pension).
        // Hors connexion : une ligne par chambre, depuis la copie locale.
        onWillStart(() => this.loadPayers());
    }

    async loadPayers() {
        try {
            this.state.payers = await this.pos.data.call(
                "resource.resource",
                "x_hotel_pos_payers",
                []
            );
        } catch {
            this.state.payers = null;
        }
    }

    get rows() {
        let rows = [];
        if (this.state.payers) {
            rows = this.state.payers.map((p) => ({
                key: `${p.partner_id}-${p.room_id}-${p.is_agency ? "a" : "g"}`,
                roomId: p.room_id,
                roomName: p.room_name,
                partnerId: p.partner_id,
                partnerName: p.partner_name,
                agencyName: p.agency_name || "",
                isAgency: p.is_agency,
                orderName: p.order_name || "",
            }));
        } else {
            for (const room of this.pos.models["resource.resource"].getAll()) {
                const partner = room.x_current_partner_id;
                if (partner) {
                    rows.push({
                        key: `${partner.id}-${room.id}-g`,
                        roomId: room.id,
                        roomName: room.name,
                        partnerId: partner.id,
                        partnerName: partner.name,
                        agencyName: "",
                        isAgency: false,
                        orderName: "",
                    });
                }
            }
        }
        const search = this.state.search.trim().toLowerCase();
        if (!search) {
            return rows;
        }
        return rows.filter(
            (r) =>
                r.roomName.toLowerCase().includes(search) ||
                r.partnerName.toLowerCase().includes(search) ||
                r.agencyName.toLowerCase().includes(search)
        );
    }

    dueOf(row) {
        return this.pos.models["res.partner"].get(row.partnerId)?.x_room_charge_due;
    }

    async selectRow(row) {
        const room = this.pos.models["resource.resource"].get(row.roomId);
        let partner = this.pos.models["res.partner"].get(row.partnerId);
        if (!partner) {
            // Contact absent de la mémoire du POS : chargé comme le fait la
            // liste native des clients (fiche complète, liste de prix comprise).
            try {
                const result = await this.pos.data.callRelated("res.partner", "get_new_partner", [
                    this.pos.config.id,
                    [["id", "=", row.partnerId]],
                    0,
                ]);
                partner = result["res.partner"]?.[0];
            } catch {
                partner = null;
            }
        }
        if (!room || !partner) {
            return;
        }
        this.props.getPayload({ partner, room });
        this.props.close();
    }
}
