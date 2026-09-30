from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Identité (complète x_nationality / x_document_* de booking_engine).
    x_birth_date = fields.Date(string="Date de naissance")
    x_birth_place = fields.Char(string="Lieu de naissance")
    x_document_expiry = fields.Date(string="Expiration de la pièce")
    x_document_issue_date = fields.Date(string="Pièce délivrée le")
    x_document_issue_place = fields.Char(string="Pièce délivrée à")

    x_room_charge_due = fields.Monetary(
        compute="_compute_room_charge_due",
        currency_field="currency_id",
    )

    def _compute_room_charge_due(self):
        for partner in self:
            orders = partner.x_ongoing_bookings.x_ongoing_booking.sale_order_id
            charges = orders.x_folio_charge_ids.filtered(
                lambda c: c.payment_status == "due"
            )
            partner.x_room_charge_due = sum(charges.mapped("amount"))

    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + ["x_ongoing_bookings", "x_room_charge_due"]