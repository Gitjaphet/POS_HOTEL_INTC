import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
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

    /**
     * Remboursement : refus si un article remboursé figure déjà sur une
     * facture active (voir pos_order_refund_guard.py). Vérifié sur le
     * serveur AVANT la validation, seul moment où l'on peut encore arrêter
     * la caisse. Serveur injoignable : refus aussi, le remboursement peut
     * attendre (23/10/2026). Vente normale : aucun changement.
     */
    async validateOrder(isForceValidate = false) {
        const refundedIds = [
            ...new Set(
                this.currentOrder.lines
                    .map((line) => line.refunded_orderline_id?.id)
                    .filter((id) => Number.isInteger(id))
            ),
        ];
        if (refundedIds.length) {
            let invoiced;
            try {
                invoiced = await this.pos.data.call(
                    "pos.order",
                    "x_hotel_refund_invoiced_lines",
                    [refundedIds]
                );
            } catch {
                this.dialog.add(AlertDialog, {
                    title: _t("Vérification impossible"),
                    body: _t(
                        "Le serveur est injoignable : impossible de vérifier que les articles " +
                        "remboursés ne sont pas déjà facturés. Réessayez dans un instant."
                    ),
                });
                return;
            }
            if (invoiced?.length) {
                const items = invoiced
                    .map((c) => `« ${c.name} » (facture ${c.invoice}${c.partner ? ", " + c.partner : ""})`)
                    .join(", ");
                this.dialog.add(AlertDialog, {
                    title: _t("Remboursement impossible"),
                    body:
                        _t("Déjà facturé : ") + items + ". " +
                        _t("Demandez à la réception d'annuler ou d'extourner cette facture avant de rembourser."),
                });
                return;
            }
        }
        return super.validateOrder(...arguments);
    },
});
