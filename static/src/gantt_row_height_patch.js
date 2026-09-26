import { patch } from "@web/core/utils/patch";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

patch(GanttRenderer.prototype, {
    getRowTypeHeight(type) {
        return { t0: 48, t1: 50, t2: 0 }[type];
    },
    getGridStyle() {
        const style = super.getGridStyle();
        return style.replace("--Gantt__Pill-height:25px", "--Gantt__Pill-height:50px");
    },
});