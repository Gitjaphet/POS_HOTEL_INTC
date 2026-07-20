from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    is_room_charge = fields.Boolean(
        string="Transfert vers chambre",
        help="Si activé, ce moyen de paiement ouvre la recherche de chambre/séjour "
             "au lieu d'encaisser directement. Le montant est imputé au folio du client.",
    )