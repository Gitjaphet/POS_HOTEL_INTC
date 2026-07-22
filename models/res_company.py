from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _create_hotel_pos_payment_methods(self):
        for company in self:
            self.env["pos.payment.method"]._ensure_room_charge_method(company)