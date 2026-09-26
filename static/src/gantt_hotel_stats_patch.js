import { patch } from "@web/core/utils/patch";
import { PlanningGanttRenderer } from "@planning/views/planning_gantt/planning_gantt_renderer";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { onWillStart, onWillUpdateProps, useState, useRef, useEffect } from "@odoo/owl";

patch(PlanningGanttRenderer.prototype, {
    setup() {
        super.setup();
        console.log("[HOTEL] setup patché exécuté");
        this.orm = useService("orm");
        this.hotelAction = useService("action");
        this.hotelStats = useState({ data: null, height: 0 });
        this._hotelStatsSeq = 0;
        if (this.isHotelPlanning) {
            onWillStart(() => this.loadHotelStats());
            onWillUpdateProps(() => this.loadHotelStats());
                        // Hauteur réelle du bloc (varie : retour à la ligne, mobile) →
            // relue par getGridStyle() pour décaler les en-têtes sticky.
            this.hotelStatsRef = useRef("hotelStats");
            useEffect(
                (el) => {
                    if (!el) {
                        return;
                    }
                    const observer = new ResizeObserver(() => {
                        this.hotelStats.height = el.offsetHeight;
                    });
                    observer.observe(el);
                    return () => observer.disconnect();
                },
                () => [this.hotelStatsRef.el]
            );
        }
    },

    get isHotelPlanning() {
        const fields = this.model.metaData.decorationFields || [];
        console.log("[HOTEL] decorationFields =", fields);
        return fields.includes("x_stay_status");
    },

    getGridStyle() {
        const style = super.getGridStyle();
        const height = this.hotelStats?.height;
        return height ? `${style};--Hotel__Stats-height:${height}px` : style;
    },

    async getPopoverProps(pill) {
        const props = await super.getPopoverProps(...arguments);
        if (!this.isHotelPlanning) {
            return props;
        }
        // Planning hôtel : ni Déprogrammer ni Supprimer depuis le planning.
        // Le Python fournit l'action d'ouverture du folio avec le formulaire
        // hôtel ; False = devis sans commande, qui garde « Modifier ».
        const action = await this.orm.call("planning.slot", "action_open_hotel_folio", [[pill.record.id]]);
        if (!action) {
            props.buttons = props.buttons.slice(0, 1);
            return props;
        }
        props.buttons = [{
            text: "Ouvrir la fiche",
            class: "btn btn-sm btn-primary",
            onClick: () => this.hotelAction.doAction(action),
        }];
        return props;
    },


    // Le bloc est frère de la grille, pas enfant : il n'hérite pas de
    // --Gantt__RowHeader-width. On la lui repasse pour aligner la colonne
    // du logo sur celle des chambres.
    get hotelStatsStyle() {
        return `--Gantt__RowHeader-width:${this.rowHeaderWidth}px`;
    },

    // Société principale active (sélecteur multi-société), pas la société
    // par défaut de l'utilisateur.
    get hotelCompanyLogoUrl() {
        return `/web/image/res.company/${user.activeCompany.id}/logo`;
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