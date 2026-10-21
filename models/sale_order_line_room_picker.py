from odoo import api, fields, models


class SaleOrderLine(models.Model):
    """Choix direct du numéro de chambre sur une ligne de réservation.

    Le menu « Choisir une chambre » propose les chambres libres sur les dates
    de la ligne (à défaut, celles du séjour), tous types confondus ; le choix
    remplit le produit (le type) et, à l'enregistrement, crée le créneau sur
    cette chambre par _generate_missing_room_slots (même mécanique que ⊕).

    Fichier séparé : sale_order_line.py n'est pas modifié. create() appelle
    d'abord tout le create() existant (dates, prix, synchronisations).
    """
    _inherit = "sale.order.line"

    x_requested_room_id = fields.Many2one(
        "resource.resource", string="Chambre demandée", copy=False,
        domain="[('id', 'in', x_available_room_ids)]",
        help="Chambre choisie à la création de la ligne. copy=False : une "
             "ligne copiée en interne (départ ou arrivée décalés) ne crée "
             "jamais de créneau supplémentaire.",
    )
    x_available_room_ids = fields.Many2many(
        "resource.resource", string="Chambres libres",
        compute="_compute_x_available_room_ids",
    )

    @api.depends(
        "x_room_start_date", "x_room_return_date",
        "order_id.rental_start_date", "order_id.rental_return_date",
    )
    def _compute_x_available_room_ids(self):
        """Chambres libres, tous types : même règle que
        _get_free_room_resources (créneaux qui se chevauchent, fermetures),
        mais sans se limiter au type du produit de la ligne."""
        Resource = self.env["resource.resource"]
        rooms = Resource.search(Resource._get_room_resource_domain())
        for line in self:
            start = line.x_room_start_date or line.order_id.rental_start_date
            stop = line.x_room_return_date or line.order_id.rental_return_date
            if not rooms or not start or not stop:
                line.x_available_room_ids = False
                continue
            slot_domain = [
                ("resource_id", "in", rooms.ids),
                ("start_datetime", "<=", stop),
                ("end_datetime", ">=", start),
            ]
            if line._origin.id:
                slot_domain.append(("sale_line_id", "!=", line._origin.id))
            busy = self.env["planning.slot"].search(slot_domain).resource_id
            closed = self.env["resource.calendar.leaves"].search([
                ("resource_id", "in", rooms.ids),
                ("date_from", "<=", stop),
                ("date_to", ">=", start),
            ]).resource_id
            line.x_available_room_ids = rooms - busy - closed

    @api.onchange("x_requested_room_id")
    def _onchange_x_requested_room_id(self):
        """Le type (produit) suit la chambre choisie : même choix de produit
        que planning.slot.action_create_order natif (premier produit louable
        du rôle de la chambre)."""
        room = self.x_requested_room_id
        if not room:
            return
        role = room.default_role_id
        if self.product_id.planning_role_id == role:
            return
        template = role.product_ids.filtered("rent_ok")[:1]
        if template:
            self.product_id = template.product_variant_id

    @api.model_create_multi
    def create(self, vals_list):
        # Une offre de chambre est toujours une location : sans is_rental,
        # toute la mécanique hôtelière (créneaux, dates, confirmation)
        # ignorait la ligne (cas d'une ligne ajoutée depuis le formulaire
        # des Réservations, 21/10/2026).
        Product = self.env["product.product"]
        for vals in vals_list:
            if vals.get("product_id"):
                product = Product.browse(vals["product_id"])
                if product.rent_ok and product.planning_role_id.x_is_a_room_offer:
                    vals["is_rental"] = True
        lines = super().create(vals_list)
        # Créneau UNIQUEMENT pour une chambre choisie explicitement, et
        # seulement si la ligne n'en a pas déjà (Planning : créneau rattaché
        # dès la création). La confirmation d'un devis n'en crée pas de
        # second : Odoo ignore les lignes dont les heures sont déjà planifiées.
        for line in lines.filtered(
            lambda l: l.x_requested_room_id
            and l.x_is_a_room_offer
            and l.is_rental
            and not l.planning_slot_ids
            and l.order_id.state != "cancel"
        ):
            line._generate_missing_room_slots(forced_resource_id=line.x_requested_room_id.id)
        return lines
