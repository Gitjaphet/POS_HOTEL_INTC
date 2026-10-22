import { patch } from "@web/core/utils/patch";
import { PlanningGanttRenderer } from "@planning/views/planning_gantt/planning_gantt_renderer";

// Barres de chambre en vue Semaine et Mois (cases en demi-journée) :
// 1. RANGEMENT — règle de midi des PMS (« tape chart ») : la case réservée
//    dans la grille va de midi (arrivée) à midi (départ) ; un séjour d'un
//    seul jour occupe la matinée. Un départ et une arrivée le même jour ne
//    s'empilent jamais.
// 2. DESSIN — la barre colorée est décalée aux heures RÉELLES par des marges
//    en pourcentage de cette case (pill.hotelStyle) : arrivée à 20:00 =
//    début de barre à 20:00, départ à 16:55 = fin de barre à 16:55.
// Aucune colonne supplémentaire, aucune constante d'Odoo modifiée ; la vue
// Jour reste native. Redimensionnement désactivé sur ces barres (il
// remplacerait l'heure réelle) ; les dates se modifient dans la fiche.
patch(PlanningGanttRenderer.prototype, {
    getPill(record) {
        const pill = super.getPill(...arguments);
        if (!this.isHotelPlanning || !record.sale_line_id) {
            return pill;
        }
        const { dateStartField, dateStopField, globalStart, globalStop, scale } =
            this.model.metaData;
        if (scale.interval !== "day" || scale.cellPart < 2) {
            return pill; // vue Jour (à l'heure) ou Année : affichage natif
        }
        const realStart = record[dateStartField];
        const realStop = record[dateStopField];
        if (!realStart || !realStop) {
            return pill;
        }
        const noon = (d) => d.set({ hour: 12, minute: 0, second: 0, millisecond: 0 });
        let boxStart;
        let boxStop;
        if (realStart.hasSame(realStop, "day")) {
            boxStart = realStart.startOf("day");
            boxStop = noon(realStop);
        } else {
            boxStart = noon(realStart);
            boxStop = noon(realStop);
        }
        const clamp = (d) => (d < globalStart ? globalStart : d > globalStop ? globalStop : d);
        const shownBoxStart = clamp(boxStart);
        const shownBoxStop = clamp(boxStop);
        if (shownBoxStop <= shownBoxStart) {
            return pill;
        }
        pill.grid = { ...pill.grid, column: this.getGridColumnFromDates(shownBoxStart, shownBoxStop) };
        pill.disableStartResize = true;
        pill.disableStopResize = true;

        // Dessin aux heures réelles (bornées à la période affichée).
        const boxMs = shownBoxStop.toMillis() - shownBoxStart.toMillis();
        const leftMs = clamp(realStart).toMillis() - shownBoxStart.toMillis();
        const rightMs = shownBoxStop.toMillis() - clamp(realStop).toMillis();
        const pct = (ms) => ((ms / boxMs) * 100).toFixed(3);
        pill.hotelStyle = `margin-left: ${pct(leftMs)}%; margin-right: ${pct(rightMs)}%;`;
        return pill;
    },
});
