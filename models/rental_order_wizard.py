from odoo import models, _
from odoo.exceptions import UserError


class RentalOrderWizardLine(models.TransientModel):
    _inherit = 'rental.order.wizard.line'

    def _apply(self):
        for wizard_line in self:
            if wizard_line.status == 'return' and wizard_line.qty_returned > 0:
                order = wizard_line.order_line_id.order_id
                if not order.currency_id.is_zero(order.x_folio_total_due):
                    raise UserError(_(
                        "Check-out impossible : le folio %(name)s a encore %(amount)s "
                        "de consommations non réglées. Réglez-les avant le départ."
                    ) % {
                        'name': order.name,
                        'amount': order.x_folio_total_due,
                    })
        return super()._apply()