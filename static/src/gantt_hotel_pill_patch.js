import { patch } from "@web/core/utils/patch";
import { PlanningGanttRenderer } from "@planning/views/planning_gantt/planning_gantt_renderer";

// Barres du planning hôtel : une classe par statut de séjour, colorée en SCSS
// avec les mêmes couleurs que les tuiles du tableau de bord (vert attendu,
// bleu en séjour, violet parti). Les devis (sans ligne de commande) gardent
// la couleur grise native.
patch(PlanningGanttRenderer.prototype, {
    enrichPill() {
        const pill = super.enrichPill(...arguments);
        const { record } = pill;
        if (this.isHotelPlanning && record.sale_line_id && record.x_stay_status) {
            pill.className += ` o_hotel_pill o_hotel_pill_${record.x_stay_status}`;
        }
        return pill;
    },

    /** Fond = couleur de la source ; texte noir ou blanc selon la luminosité. */
    hotelSourceStyle(record) {
        const bg = record.x_booking_source_color || "#6C757D";
        const hex = bg.replace("#", "");
        if (!/^[0-9a-fA-F]{6}$/.test(hex)) {
            return `background-color: ${bg}; color: #fff;`;
        }
        const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
        const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
        return `background-color: ${bg}; color: ${luminance > 0.6 ? "#000" : "#fff"};`;
    },
});
