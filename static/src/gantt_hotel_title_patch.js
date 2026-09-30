/** @odoo-module **/
// Planning hôtel : « Nouvelle réservation » au lieu de « Ajouter un poste »
// dans la fenêtre de création. Seulement sous le contexte hotel_planning ;
// l'app Planning standard et les séjours existants ne changent pas.
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { GanttController } from "@web_gantt/gantt_controller";

patch(GanttController.prototype, {
    openDialog(props, options) {
        if (this.props.context?.hotel_planning && !props.resId) {
            props = { ...props, title: _t("Nouvelle réservation") };
        }
        return super.openDialog(props, options);
    },
});
