import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { RoomChargePopup } from "@POS_HOTEL_INTC/app/screens/payment_screen/room_charge_popup/room_charge_popup";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        const hasSettleDueLine = this.currentOrder?.lines?.some(
            (line) => line.isSettleDueLine?.()
        );
        if (hasSettleDueLine) {
            this.payment_methods_from_config = this.payment_methods_from_config.filter(
                (pm) => !pm.is_room_charge
            );
        }
    },

    async openRoomChargePopup() {
        const partner = await makeAwaitable(this.dialog, RoomChargePopup, {});
        if (partner) {
            this.pos.setPartnerToCurrentOrder(partner);
        }
    },

    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.is_room_charge) {
            const partner = await makeAwaitable(this.dialog, RoomChargePopup, {});
            if (!partner) {
                return false;
            }
            this.pos.setPartnerToCurrentOrder(partner);
        }
        return super.addNewPaymentLine(...arguments);
    },
});