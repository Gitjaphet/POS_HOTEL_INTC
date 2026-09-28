from odoo import api, fields, models
from odoo.exceptions import UserError


class PosHotelChangeRoomWizard(models.TransientModel):
    _name = "pos.hotel.change.room.wizard"
    _description = "Changer de chambre"

    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne",
        required=True,
        readonly=True,
    )
    slot_id = fields.Many2one(
        "planning.slot",
        string="Chambre concernée",
        required=True,
        domain="[('sale_line_id', '=', sale_order_line_id)]",
    )
    current_resource_id = fields.Many2one(
        related="slot_id.resource_id",
        string="Chambre actuelle",
    )
    available_resource_ids = fields.Many2many(
        "resource.resource",
        compute="_compute_available_resource_ids",
    )
    new_resource_id = fields.Many2one(
        "resource.resource",
        string="Nouvelle chambre",
        required=True,
        domain="[('id', 'in', available_resource_ids)]",
    )
    type_changed = fields.Boolean(
        compute="_compute_type_changed",
    )
    pricing_mode = fields.Selection(
        [
            ("upgrade", "Surclassement gratuit (tarif réservé conservé)"),
            ("reprice", "Appliquer le tarif du nouveau type"),
        ],
        string="Tarif",
        default="upgrade",
    )
    available_product_ids = fields.Many2many(
        "product.product",
        compute="_compute_available_product_ids",
    )
    new_product_id = fields.Many2one(
        "product.product",
        string="Nouveau produit",
        compute="_compute_new_product_id",
        store=True,
        readonly=False,
        domain="[('id', 'in', available_product_ids)]",
    )
    reason = fields.Text(string="Motif")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        line = self.env["sale.order.line"].browse(vals.get("sale_order_line_id"))
        if line and "slot_id" in fields_list and not vals.get("slot_id"):
            vals["slot_id"] = line.planning_slot_ids[:1].id
        return vals

    @api.depends("slot_id")
    def _compute_available_resource_ids(self):
        """Chambres libres sur les dates du créneau, tous types confondus :
        ni séjour non terminé qui chevauche (même règle que l'anti double
        réservation), ni indisponibilité (entretien, travaux)."""
        Resource = self.env["resource.resource"]
        for wizard in self:
            slot = wizard.slot_id
            if not (slot and slot.start_datetime and slot.end_datetime):
                wizard.available_resource_ids = False
                continue
            rooms = Resource.search(Resource._get_room_resource_domain())
            busy = self.env["planning.slot"].search([
                ("id", "!=", slot.id),
                ("resource_id", "in", rooms.ids),
                ("x_stay_status", "!=", "checked_out"),
                ("start_datetime", "<", slot.end_datetime),
                ("end_datetime", ">", slot.start_datetime),
            ]).resource_id
            unavailable = self.env["resource.calendar.leaves"].search([
                ("resource_id", "in", rooms.ids),
                ("date_from", "<", slot.end_datetime),
                ("date_to", ">", slot.start_datetime),
            ]).resource_id
            wizard.available_resource_ids = rooms - busy - unavailable - slot.resource_id

    @api.depends("slot_id", "new_resource_id")
    def _compute_type_changed(self):
        # Même règle que le blocage du glisser-déposer
        # (planning.slot._x_check_room_type) ; role_ids plutôt que
        # default_role_id, réservé au groupe RH.
        for wizard in self:
            new_roles = wizard.new_resource_id.role_ids
            wizard.type_changed = bool(
                wizard.new_resource_id
                and new_roles
                and wizard.slot_id.role_id not in new_roles
            )

    @api.depends("new_resource_id")
    def _compute_available_product_ids(self):
        # Produits de location du nouveau type (rôle de la chambre), comme
        # action_create_order (role.product_ids filtré sur rent_ok).
        for wizard in self:
            role = wizard.new_resource_id.role_ids[:1]
            templates = role.product_ids.filtered("rent_ok") if role else self.env["product.template"]
            wizard.available_product_ids = templates.product_variant_ids

    @api.depends("available_product_ids")
    def _compute_new_product_id(self):
        # Variante équivalente : mêmes valeurs d'attributs que le produit
        # réservé (ex. « Petit déjeuner inclus »), sinon la première.
        for wizard in self:
            candidates = wizard.available_product_ids
            current = wizard.sale_order_line_id.product_id
            names = set(current.product_template_attribute_value_ids.mapped("name"))
            match = candidates.filtered(
                lambda p: set(p.product_template_attribute_value_ids.mapped("name")) == names
            )
            wizard.new_product_id = (match or candidates)[:1]

    def action_confirm_change_room(self):
        self.ensure_one()
        slot = self.slot_id
        line = self.sale_order_line_id
        old_resource = slot.resource_id
        new_resource = self.new_resource_id
        reason = (self.reason or "").strip()

        # 1. Vérifications (la chambre a pu être réservée entre-temps).
        if new_resource not in self.available_resource_ids:
            raise UserError("La chambre %s n'est plus disponible sur ces dates." % new_resource.name)
        if self.type_changed and not reason:
            raise UserError("Indiquez le motif du changement de type de chambre.")
        reprice = self.type_changed and self.pricing_mode == "reprice"
        if reprice and not self.new_product_id:
            raise UserError(
                "Aucun produit de location n'est associé au type de la chambre %s." % new_resource.name
            )

        # 2. Nouveau tarif : isoler la chambre sur sa propre ligne avant de
        # changer le produit (réutilise le découpage de _adjust_room_stay_date,
        # date de début inchangée).
        if reprice:
            line = line._adjust_room_stay_date(slot, "start", slot.start_datetime)

        # 3. Déplacement volontaire : x_room_type_change franchit le blocage
        # du glisser-déposer entre types ; le rôle suit la nouvelle chambre.
        slot_vals = {"resource_id": new_resource.id}
        if self.type_changed:
            slot_vals["role_id"] = new_resource.role_ids[:1].id
        slot.with_context(x_room_type_change=True).write(slot_vals)

        # 4. Nouveau tarif : produit du nouveau type, prix recalculé (règle
        # des nuits hôtelières). Surclassement : ligne inchangée.
        if reprice:
            # in_rental_app : sans ce contexte, _compute_is_rental (sale_renting)
            # repasse la ligne en vente simple (prix catalogue, plus de dates).
            line.with_context(in_rental_app=True).write({
                "product_id": self.new_product_id.id,
                "is_rental": True,
            })
            line.price_unit = line._get_pricelist_price()
            self.env.add_to_compute(line._fields["name"], line)

        # 5. Traçabilité : historique des chambres + fil de discussion.
        pricing = self.pricing_mode if self.type_changed else "same_type"
        pricing_label = dict(
            self.env["pos.hotel.room.removal.log"]._fields["pricing_mode"].selection
        )[pricing]
        self.env["pos.hotel.room.removal.log"].create({
            "event_type": "change",
            "sale_order_id": line.order_id.id,
            "sale_order_line_id": line.id,
            "resource_id": old_resource.id,
            "resource_name": old_resource.name or "",
            "new_resource_id": new_resource.id,
            "new_resource_name": new_resource.name,
            "pricing_mode": pricing,
            "reason": reason or "Changement de chambre (même type)",
        })
        line.order_id.message_post(
            body="Changement de chambre : %s → %s (%s)%s" % (
                old_resource.name, new_resource.name, pricing_label,
                (" — motif : %s" % reason) if reason else "",
            )
        )
        return {"type": "ir.actions.act_window_close"}
