from markupsafe import Markup, escape

from odoo import api, fields, models


class PosHotelFolioCharge(models.Model):
    """Affichage des formules (combos) dans l'onglet Extra : la formule, puis
    ses articles en dessous, comme sur le ticket du POS. Champs calculés non
    stockés, lus depuis la ligne POS de la charge (ligne mère du combo)."""
    _inherit = "pos.hotel.folio.charge"

    x_combo_detail = fields.Text(
        string="Détail de la formule",
        compute="_compute_x_combo_display",
    )
    x_name_html = fields.Html(
        string="Description",
        compute="_compute_x_combo_display",
        sanitize=False,
    )

    @api.depends("name", "pos_order_line_id.combo_line_ids.full_product_name")
    def _compute_x_combo_display(self):
        for charge in self:
            items = charge.pos_order_line_id.combo_line_ids.mapped("full_product_name")
            charge.x_combo_detail = "\n".join(items)
            html = escape(charge.name or "")
            for item in items:
                html += Markup('<br/><small class="text-muted">· %s</small>') % item
            charge.x_name_html = html
