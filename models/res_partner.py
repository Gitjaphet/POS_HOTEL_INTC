from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        return fields + ["x_ongoing_bookings"]