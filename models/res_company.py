from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Enregistrement des occupants (fiche de police). Rien d'obligatoire par
    # défaut : chaque hôtel choisit son périmètre dans Paramètres > Hôtel.
    x_guest_registration_scope = fields.Selection(
        [
            ("none", "Aucun"),
            ("main", "Occupant principal de chaque chambre"),
            ("adults", "Tous les adultes"),
            ("all", "Tous les occupants (enfants compris)"),
        ],
        string="Occupants à enregistrer", default="none", required=True,
    )
    x_guest_registration_mode = fields.Selection(
        [("warn", "Avertir"), ("block", "Bloquer l'arrivée")],
        string="Si incomplet à l'arrivée", default="warn", required=True,
    )
    x_guest_require_nationality = fields.Boolean(string="Nationalité obligatoire")
    x_guest_require_document = fields.Boolean(string="Pièce d'identité obligatoire")
    x_guest_require_birth_date = fields.Boolean(string="Date de naissance obligatoire")
    x_guest_require_travel = fields.Boolean(string="Provenance / destination obligatoires")
    x_police_card_footer = fields.Text(string="Mention en bas de la fiche de police")

    def _create_hotel_pos_payment_methods(self):
        for company in self:
            self.env["pos.payment.method"]._ensure_room_charge_method(company)