import { patch } from "@web/core/utils/patch";
import { PlanningGanttRenderer } from "@planning/views/planning_gantt/planning_gantt_renderer";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

// Indicateur de chambre du planning hôtel, à gauche du nom (toujours
// visible, quelle que soit la période affichée), une seule icône par chambre :
// réveil = départ dépassé non effectué ; balai rouge = à nettoyer (clic ->
// Propre) ; sablier = arrivée non effectuée (no-show) ; balai vert = propre
// et prête ; vide = client en séjour ou chambre attendue. Réveil et sablier :
// clic -> ouvre la réservation. États calculés côté serveur en un seul appel
// (get_hotel_broom_states).
patch(PlanningGanttRenderer.prototype, {
    setup() {
        super.setup();
        this.hotelBrooms = useState({ data: {} });
        this._hotelBroomsSeq = 0;
        if (this.isHotelPlanning) {
            this.hotelBroomOrm = useService("orm");
            this.hotelBroomDialog = useService("dialog");
            this.hotelBroomAction = useService("action");
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

    _getHotelBroomEntry(row) {
        if (!this.isHotelPlanning || !this.hasAvatar(row)) {
            return null;
        }
        const props = this.getAvatarProps(row);
        if (!props.isResourceMaterial || !props.resId) {
            return null;
        }
        return this.hotelBrooms.data[props.resId] || { state: "none", title: "" };
    },

    /**
     * false : pas une ligne de chambre (rien n'est affiché) ;
     * 'none' : chambre sans indicateur (emplacement vide : alignement) ;
     * 'late' | 'dirty' | 'noshow' | 'clean' : réveil, balai rouge, sablier
     * ou balai vert.
     */
    getHotelBroom(row) {
        const entry = this._getHotelBroomEntry(row);
        return entry ? entry.state : false;
    },

    getHotelBroomTitle(row) {
        const entry = this._getHotelBroomEntry(row);
        return entry ? entry.title : "";
    },

    async onHotelBroomClick(row) {
        const props = this.getAvatarProps(row);
        const state = this.getHotelBroom(row);
        if (state === "late" || state === "noshow") {
            const action = await this.hotelBroomOrm.call(
                "resource.resource", "action_hotel_open_late_folio", [[props.resId]]
            );
            if (action) {
                await this.hotelBroomAction.doAction(action);
            }
            return;
        }
        if (state !== "dirty") {
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
