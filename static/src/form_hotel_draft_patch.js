import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

// Brouillon de réservation ouvert par « Créer la réservation » (planning
// hôtel) : le créneau du planning est déjà enregistré à ce moment-là. Si le
// brouillon est abandonné, on demande sa suppression au serveur, qui ne
// supprime qu'un créneau chambre encore sans commande.
patch(FormController.prototype, {
    // Croix « X » du formulaire.
    async discard() {
        const slotId = this._hotelDraftSlotId();
        if (slotId) {
            await this._hotelDropDraftSlot(slotId);
        }
        return super.discard(...arguments);
    },

    // Départ par le fil d'Ariane ou un menu, avec ou sans modification.
    async beforeLeave() {
        const slotId = this._hotelDraftSlotId();
        const canLeave = await super.beforeLeave(...arguments);
        // Toujours neuve après beforeLeave = jamais enregistrée : abandon.
        // canLeave === false : l'utilisateur a choisi de rester.
        if (slotId && canLeave !== false && this.model.root.isNew) {
            await this._hotelDropDraftSlot(slotId);
        }
        return canLeave;
    },

    _hotelDraftSlotId() {
        const root = this.model.root;
        if (root?.resModel !== "sale.order" || !root.isNew) {
            return false;
        }
        return root.context?.hotel_draft_slot_id || false;
    },

    async _hotelDropDraftSlot(slotId) {
        // Service ORM de l'environnement (non lié au composant) : l'appel doit
        // aboutir même si le formulaire est détruit juste après.
        await this.env.services.orm.call("planning.slot", "action_discard_hotel_draft", [[slotId]]);
    },
});
