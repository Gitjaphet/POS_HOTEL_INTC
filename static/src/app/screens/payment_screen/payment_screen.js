import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { RoomChargePopup } from "@POS_HOTEL_INTC/app/screens/payment_screen/room_charge_popup/room_charge_popup";

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.is_room_charge) {
            const partner = await new Promise((resolve) => {
                this.dialog.add(RoomChargePopup, {
                    getPayload: (selectedPartner) => resolve(selectedPartner),
                });
            });
            if (!partner) {
                return false;
            }
            this.currentOrder.setPartner(partner);
        }
        return super.addNewPaymentLine(...arguments);
    },
});