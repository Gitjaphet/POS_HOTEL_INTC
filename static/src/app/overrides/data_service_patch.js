import { patch } from "@web/core/utils/patch";
import { PosData } from "@point_of_sale/app/services/data_service";

patch(PosData.prototype, {
    async setup(env, deps) {
        await super.setup(env, deps);
        this.connectWebSocket("ROOM_OCCUPANCY_UPDATED", this.onRoomOccupancyUpdated.bind(this));
    },

    async onRoomOccupancyUpdated() {
        const roomIds = this.models["resource.resource"].getAll().map((room) => room.id);
        if (!roomIds.length) {
            return;
        }
        await this.read(
            "resource.resource",
            roomIds,
            ["id", "name", "x_occupant_ids", "x_current_partner_id"]
        );
    },
});