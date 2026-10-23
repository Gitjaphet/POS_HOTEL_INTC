from odoo import api, fields, models


class SaleOrder(models.Model):
    """Réservation d'agence.

    - L'agence reçoit la facture des nuits : l'adresse de facturation native
      (partner_invoice_id, calculée depuis le client) devient l'agence tant
      qu'elle est renseignée, et redevient celle du client si on la retire.
    - « Pension prise en charge par l'agence » : fait apparaître l'agence
      dans la fenêtre Transfert Chambre du POS, pour que le barman y mette
      les repas de pension. Chaque client paie ses propres consommations,
      choisies à son nom au POS (23/10/2026).
    """
    _inherit = "sale.order"

    x_agency_partner_id = fields.Many2one(
        "res.partner",
        string="Agence",
        domain="[('is_company', '=', True)]",
        index=True,
        help="Agence de voyage qui paie les nuits : la facture de la chambre "
             "lui est adressée. Les consommations de chaque client restent à "
             "son nom.",
    )
    x_agency_pays_board = fields.Boolean(
        string="Pension prise en charge par l'agence",
        help="Si coché, le POS propose l'agence dans la fenêtre Transfert "
             "Chambre : le barman y met les repas compris dans le contrat.",
    )

    @api.depends("partner_id", "x_agency_partner_id")
    def _compute_partner_invoice_id(self):
        super()._compute_partner_invoice_id()
        for order in self.filtered("x_agency_partner_id"):
            order.partner_invoice_id = order.x_agency_partner_id.address_get(["invoice"])["invoice"]

    @api.onchange("x_agency_partner_id")
    def _onchange_x_agency_partner_id(self):
        if not self.x_agency_partner_id:
            self.x_agency_pays_board = False
