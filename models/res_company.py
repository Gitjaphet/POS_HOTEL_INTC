from odoo import fields, models

# Comptes de l'hôtel (24/10/2026) : jamais cherchés par numéro dans le code.
# Clé -> (champ de la société, méthode pos.payment.method qui trouve le compte
# par son numéro par défaut ou le crée). Numéros par défaut : 411200, 411300,
# 707200, 707300 ; le client peut les renuméroter ou en choisir d'autres
# dans Paramètres > Hôtel.
X_HOTEL_ACCOUNTS = {
    "extras_receivable": ("x_hotel_extras_receivable_account_id", "_ensure_extras_receivable_account"),
    "services_receivable": ("x_hotel_services_receivable_account_id", "_ensure_service_charge_account"),
    "extras_income": ("x_hotel_extras_income_account_id", "_ensure_extras_income_account"),
    "services_income": ("x_hotel_services_income_account_id", "_ensure_service_income_account"),
}


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
    x_police_card_footer = fields.Text(string="Déclaration signée par le client")

    # Comptes de l'hôtel : lus UNIQUEMENT par _x_hotel_account().
    x_hotel_extras_receivable_account_id = fields.Many2one(
        "account.account", string="Créances extras (transferts chambre)",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Par défaut 411200. Créance des consommations transférées sur une chambre.",
    )
    x_hotel_services_receivable_account_id = fields.Many2one(
        "account.account", string="Créances services chambre",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Par défaut 411300. Créance des services ajoutés au séjour.",
    )
    x_hotel_extras_income_account_id = fields.Many2one(
        "account.account", string="Ventes extras chambre",
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help="Par défaut 707200.",
    )
    x_hotel_services_income_account_id = fields.Many2one(
        "account.account", string="Ventes services chambre",
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help="Par défaut 707300.",
    )

    def _x_hotel_account(self, key):
        """LE point d'accès aux comptes de l'hôtel (clés de X_HOTEL_ACCOUNTS).
        Réglage vide (installation, base existante) : le compte au numéro par
        défaut est trouvé ou créé, puis mémorisé dans le réglage."""
        self.ensure_one()
        field_name, ensure_method = X_HOTEL_ACCOUNTS[key]
        account = self[field_name]
        if not account:
            account = getattr(self.env["pos.payment.method"].sudo(), ensure_method)(self)
            self.sudo()[field_name] = account
        return account

    def _x_hotel_fill_accounts(self):
        """Remplit les quatre réglages (installation, migration)."""
        for company in self:
            for key in X_HOTEL_ACCOUNTS:
                company._x_hotel_account(key)

    def _create_hotel_pos_payment_methods(self):
        for company in self:
            self.env["pos.payment.method"]._ensure_room_charge_method(company)
