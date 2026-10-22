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

    /**
     * Rattache la commande à l'occupant de la chambre choisie, sans
     * recalcul de prix inutile ni dangereux :
     * - même client que la commande : rien à faire ;
     * - remboursement : on change seulement le client, les prix restent ceux
     *   de la vente d'origine (le recalcul natif des combos plantait sur une
     *   commande de remboursement : setPricelist, 22/10/2026) ;
     * - vente normale : comportement natif (liste de prix du client).
     */
    _setRoomOccupant(partner, room) {
        const order = this.currentOrder;
        if (order.partner_id?.id !== partner.id) {
            const isRefund = order.lines.some((line) => line.refunded_orderline_id);
            if (isRefund) {
                order.update({ partner_id: partner });
            } else {
                this.pos.setPartnerToCurrentOrder(partner);
            }
        }
        order.update({ x_room_charge_resource_id_int: room.id });
    },

    async openRoomChargePopup() {
        const result = await makeAwaitable(this.dialog, RoomChargePopup, {});
        if (result) {
            this._setRoomOccupant(result.partner, result.room);
        }
    },

    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.is_room_charge) {
            const result = await makeAwaitable(this.dialog, RoomChargePopup, {});
            if (!result) {
                return false;
            }
            this._setRoomOccupant(result.partner, result.room);
        }
        return super.addNewPaymentLine(...arguments);
    },
});
