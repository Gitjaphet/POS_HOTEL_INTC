import { patch } from "@web/core/utils/patch";
import { PlanningGanttRenderer } from "@planning/views/planning_gantt/planning_gantt_renderer";

// Règle de midi des PMS (« tape chart ») pour les barres de chambre, en vue
// Semaine et Mois (cases en demi-journée) : l'arrivée s'affiche à partir de
// midi, le départ jusqu'à midi, un séjour d'un seul jour sur la matinée.
// Un départ et une arrivée le même jour tiennent ainsi sur une seule ligne.
// Affichage uniquement : les heures réelles restent dans la réservation et
// dans le texte de la barre. Le redimensionnement est désactivé sur ces
// barres (il remplacerait l'heure réelle par midi) ; les dates se modifient
// dans la fiche.
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
        let start = record[dateStartField];
        let stop = record[dateStopField];
        if (!start || !stop) {
            return pill;
        }
        const noon = (d) => d.set({ hour: 12, minute: 0, second: 0, millisecond: 0 });
        if (start.hasSame(stop, "day")) {
            start = start.startOf("day");
            stop = noon(stop);
        } else {
            start = noon(start);
            stop = noon(stop);
        }
        const shownStart = start < globalStart ? globalStart : start;
        const shownStop = stop > globalStop ? globalStop : stop;
        if (shownStop <= shownStart) {
            return pill;
        }
        pill.grid = { ...pill.grid, column: this.getGridColumnFromDates(shownStart, shownStop) };
        pill.disableStartResize = true;
        pill.disableStopResize = true;
        return pill;
    },
});
