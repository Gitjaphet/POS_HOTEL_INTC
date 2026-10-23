from markupsafe import Markup, escape

from odoo import api, fields, models


class PosHotelFolioCharge(models.Model):
    """Affichage des consommations dans les onglets Extra / Service :
    - formules (combos) : la formule, puis ses articles en dessous, comme sur
      le ticket du POS ;
    - statut affiché : « Remboursé » pour une consommation remboursée
      intégralement, « Facturé » pour une consommation due déjà mise sur une
      facture active, au lieu de « Dû ». Le statut comptable réel
      (payment_status) ne change pas.
    Champs calculés non stockés."""
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
    x_status_display = fields.Selection(
        [
            ("due", "Dû"),
            ("invoiced", "Facturé"),
            ("paid_pos", "Payé au POS"),
            ("settled", "Réglé"),
            ("cancelled", "Annulé"),
            ("refunded", "Remboursé"),
        ],
        string="Statut",
        compute="_compute_x_status_display",
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

    @api.depends("payment_status", "refund_status", "x_invoice_is_active")
    def _compute_x_status_display(self):
        for charge in self:
            if charge.refund_status == "full" and not charge.is_refund:
                charge.x_status_display = "refunded"
            elif charge.payment_status == "due" and charge.x_invoice_is_active:
                charge.x_status_display = "invoiced"
            else:
                charge.x_status_display = charge.payment_status

    def _x_is_invoiceable(self):
        """Consommation à mettre sur une facture : due, pas un remboursement,
        montant net non nul, et PAS déjà sur une facture active (brouillon ou
        confirmée). Une facture annulée ou extournée la rend de nouveau
        facturable (x_invoice_is_active passe à faux). Sans ce dernier
        critère, une seconde facture reprenait les consommations déjà
        facturées (23/10/2026)."""
        self.ensure_one()
        return (
            self.payment_status == "due"
            and not self.is_refund
            and not self.x_invoice_is_active
            and not self.currency_id.is_zero(self.amount_net)
        )

    def _x_is_invoiceable_prepaid(self):
        """Consommation déjà réglée (à la réception ou au POS) pouvant figurer
        sur une facture finale complète, avec son paiement déduit
        (account_move_prepaid.py) : pas un remboursement, montant net non nul,
        pas déjà sur une facture active."""
        self.ensure_one()
        return (
            self.payment_status in ("settled", "paid_pos")
            and not self.is_refund
            and not self.x_invoice_is_active
            and not self.currency_id.is_zero(self.amount_net)
        )
