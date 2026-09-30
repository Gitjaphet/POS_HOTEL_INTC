from odoo import api, fields, models
from odoo.exceptions import ValidationError

DOCUMENT_TYPES = [
    ("passport", "Passeport"),
    ("id_card", "Carte d'identité (CIN)"),
    ("driving_license", "Permis de conduire"),
    ("other", "Autre"),
]
# Valeurs de booking_engine (res.partner.x_document_type) -> les nôtres.
_BOOKING_ENGINE_DOC_TYPES = {
    "Passport": "passport",
    "ID card": "id_card",
    "Driving license": "driving_license",
}


class PosHotelStayGuest(models.Model):
    """Occupant d'une chambre pour un séjour (fiche de police, statistiques).

    Rattaché à la ligne de chambre : un groupe de N chambres a ses occupants
    chambre par chambre. Les champs d'identité sont une copie figée, préremplie
    depuis le contact : modifier le contact plus tard ne réécrit pas les
    séjours passés.
    """
    _name = "pos.hotel.stay.guest"
    _description = "Occupant du séjour"
    _order = "sale_order_line_id, is_main desc, is_child, sequence, id"

    sequence = fields.Integer(default=10)
    sale_order_line_id = fields.Many2one(
        "sale.order.line", string="Chambre", required=True,
        ondelete="cascade", index=True,
    )
    order_id = fields.Many2one(
        related="sale_order_line_id.order_id", store=True, index=True,
        string="Réservation",
    )
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    partner_id = fields.Many2one(
        "res.partner", string="Occupant", required=True, index=True,
        domain="[('is_company', '=', False)]",
    )
    is_main = fields.Boolean(string="Principal")
    is_child = fields.Boolean(string="Enfant")

    # Copie figée de l'identité au moment du séjour.
    nationality_id = fields.Many2one(
        "res.country", string="Nationalité",
        compute="_compute_identity", store=True, readonly=False,
    )
    document_type = fields.Selection(
        DOCUMENT_TYPES, string="Type de pièce",
        compute="_compute_identity", store=True, readonly=False,
    )
    document_number = fields.Char(
        string="N° de pièce",
        compute="_compute_identity", store=True, readonly=False,
    )
    document_expiry = fields.Date(
        string="Expiration",
        compute="_compute_identity", store=True, readonly=False,
    )
    birth_date = fields.Date(
        string="Date de naissance",
        compute="_compute_identity", store=True, readonly=False,
    )
    birth_place = fields.Char(
        string="Lieu de naissance",
        compute="_compute_identity", store=True, readonly=False,
    )
    checkin_date = fields.Datetime(string="Enregistré le", readonly=True)

    _unique_guest_per_room = models.Constraint(
        "UNIQUE(sale_order_line_id, partner_id)",
        "Cet occupant est déjà enregistré dans cette chambre.",
    )

    @api.depends("partner_id")
    def _compute_identity(self):
        for guest in self:
            partner = guest.partner_id
            guest.nationality_id = partner.x_nationality
            guest.document_type = _BOOKING_ENGINE_DOC_TYPES.get(partner.x_document_type)
            guest.document_number = partner.x_document_number
            guest.document_expiry = partner.x_document_expiry
            guest.birth_date = partner.x_birth_date
            guest.birth_place = partner.x_birth_place

    @api.constrains("is_main", "sale_order_line_id")
    def _check_single_main(self):
        for line in self.filtered("is_main").sale_order_line_id:
            if len(line.x_stay_guest_ids.filtered("is_main")) > 1:
                raise ValidationError(
                    "La chambre %s a plusieurs occupants principaux."
                    % line.display_name
                )
