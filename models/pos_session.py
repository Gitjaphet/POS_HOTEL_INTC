from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models_list = super()._load_pos_data_models(config)
        return models_list + ["resource.resource"]

    def _get_split_receivable_vals(self, payment, amount, amount_converted):
        vals = super()._get_split_receivable_vals(payment, amount, amount_converted)
        if payment.payment_method_id.is_room_charge:
            account = self.env["account.account"].search([
                ("code", "=", "411200"),
                ("company_ids", "in", self.company_id.id),
            ], limit=1)
            if account:
                vals["account_id"] = account.id
        return vals