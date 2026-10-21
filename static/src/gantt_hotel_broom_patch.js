import { patch } from "@web/core/utils/patch";
import { PlanningGanttRenderer } from "@planning/views/planning_gantt/planning_gantt_renderer";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

// Balai du planning hôtel : rouge = chambre à nettoyer (clic -> Propre),
// vert = propre et prête, absent = client en séjour. États calculés côté
// serveur en un seul appel (resource.resource.get_hotel_broom_states).
patch(PlanningGanttRenderer.prototype, {
    setup() {
        super.setup();
        this.hotelBrooms = useState({ data: {} });
        this._hotelBroomsSeq = 0;
        if (this.isHotelPlanning) {
            this.hotelBroomOrm = useService("orm");
            this.hotelBroomDialog = useService("dialog");
            onWillStart(() => this.loadHotelBrooms());
            onWillUpdateProps(() => this.loadHotelBrooms());
        }
    },

    async loadHotelBrooms() {
        // Anti-course : une réponse plus ancienne n'écrase jamais la dernière.
        const seq = ++this._hotelBroomsSeq;
        let states;
        try {
            states = await this.hotelBroomOrm.call("resource.resource", "get_hotel_broom_states", []);
        } catch {
            return;
        }
        if (seq === this._hotelBroomsSeq) {
            this.hotelBrooms.data = states;
        }
    },

    /** 'dirty' | 'clean' | false pour une ligne du planning. */
    getHotelBroom(row) {
        if (!this.isHotelPlanning || !this.hasAvatar(row)) {
            return false;
        }
        const props = this.getAvatarProps(row);
        if (!props.isResourceMaterial || !props.resId) {
            return false;
        }
        return this.hotelBrooms.data[props.resId] || false;
    },

    onHotelBroomClick(row) {
        const props = this.getAvatarProps(row);
        if (this.hotelBrooms.data[props.resId] !== "dirty") {
            return;
        }
        this.hotelBroomDialog.add(ConfirmationDialog, {
            title: "Ménage terminé",
            body: `Marquer la chambre ${props.displayName} comme nettoyée ?`,
            confirmLabel: "Oui, elle est propre",
            cancelLabel: "Annuler",
            confirm: async () => {
                await this.hotelBroomOrm.call("resource.resource", "action_hotel_broom_clean", [[props.resId]]);
                await this.loadHotelBrooms();
            },
            cancel: () => {},
        });
    },
});
