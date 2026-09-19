import { patch } from "@web/core/utils/patch";
import { GanttRendererControls } from "@web_gantt/gantt_renderer_controls";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

patch(GanttRendererControls.prototype, {
    setup() {
        super.setup();
        console.log("[HOTEL] setup patché exécuté");
        this.orm = useService("orm");
        this.hotelStats = useState({ data: null });
        this._hotelStatsSeq = 0;
        if (this.isHotelPlanning) {
            onWillStart(() => this.loadHotelStats());
            onWillUpdateProps(() => this.loadHotelStats());
        }
    },

    get isHotelPlanning() {
        const fields = this.model.metaData.decorationFields || [];
        console.log("[HOTEL] decorationFields =", fields);
        return fields.includes("x_stay_status");
    },

    async loadHotelStats() {
        console.log("[HOTEL] loadHotelStats appelé");
        const seq = ++this._hotelStatsSeq;
        const { startDate, stopDate } = this.model.metaData;
        let stats;
        try {
            stats = await this.orm.call(
                "planning.slot",
                "get_hotel_planning_stats",
                [],
                {
                    // Odoo attend "YYYY-MM-DD HH:mm:ss" strict et stocke en
                    // UTC : .toSQL() ajoute millisecondes et décalage (refusés
                    // par to_datetime), et sans .toUTC() les bornes locales
                    // (+03:00) décaleraient le comptage aux limites du mois.
                    period_start: startDate ? startDate.toUTC().toFormat("yyyy-MM-dd HH:mm:ss") : null,
                    period_stop: stopDate ? stopDate.toUTC().toFormat("yyyy-MM-dd HH:mm:ss") : null,
                }
            );
        } catch (e) {
            console.error("[HOTEL] échec RPC", e);
            return;
        }
        console.log("[HOTEL] stats reçues", stats);
        if (seq === this._hotelStatsSeq) {
            this.hotelStats.data = stats;
        }
    },
});