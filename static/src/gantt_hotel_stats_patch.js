import { patch } from "@web/core/utils/patch";
import { GanttRendererControls } from "@web_gantt/gantt_renderer_controls";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

patch(GanttRendererControls.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.hotelStats = useState({ data: null });
        // Jeton de séquence : seule la réponse de la dernière requête lancée
        // est affichée, sinon une navigation rapide entre deux mois peut
        // faire gagner une réponse obsolète arrivée en retard.
        this._hotelStatsSeq = 0;
        if (this.isHotelPlanning) {
            onWillStart(() => this.loadHotelStats());
            onWillUpdateProps(() => this.loadHotelStats());
        }
    },

    /**
     * Vrai uniquement sur le planning hôtel : notre vue héritée y déclare
     * x_stay_status, qu'aucune autre vue Gantt de la base ne porte. Évite
     * d'afficher des compteurs de chambres sur un planning RH, qui partage
     * pourtant le même modèle planning.slot.
     */
    get isHotelPlanning() {
        const fields = this.model.metaData.decorationFields || [];
        return fields.includes("x_stay_status");
    },

    async loadHotelStats() {
        const seq = ++this._hotelStatsSeq;
        const { startDate, stopDate } = this.model.metaData;
        let stats;
        try {
            stats = await this.orm.call(
                "planning.slot",
                "get_hotel_planning_stats",
                [],
                {
                    period_start: startDate ? startDate.toSQL() : null,
                    period_stop: stopDate ? stopDate.toSQL() : null,
                }
            );
        } catch {
            // Un tableau de bord indisponible ne doit jamais empêcher le
            // planning lui-même de s'afficher : on abandonne silencieusement.
            return;
        }
        if (seq === this._hotelStatsSeq) {
            this.hotelStats.data = stats;
        }
    },
});