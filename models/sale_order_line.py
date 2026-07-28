from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_room_resource_ids = fields.Many2many(
        'resource.resource',
        compute='_compute_x_room_resource_ids',
        string="Chambre(s)",
    )
    x_room_resource_names = fields.Char(
        compute='_compute_x_room_resource_ids',
        string="Chambre(s)",
    )
    x_room_nights = fields.Integer(
            string="Nuits",
            compute='_compute_x_room_nights',
            store=True,
        )
    x_is_a_room_offer = fields.Boolean(
        related='product_id.planning_role_id.x_is_a_room_offer',
        store=True,
        string="Est une chambre",
    )
    x_room_start_date = fields.Datetime(string="Début séjour (chambre)")
    x_room_return_date = fields.Datetime(string="Fin séjour (chambre)")

    @api.depends('planning_slot_ids.resource_id')
    def _compute_x_room_resource_ids(self):
        for line in self:
            resources = line.planning_slot_ids.resource_id
            line.x_room_resource_ids = resources
            line.x_room_resource_names = ", ".join(resources.mapped('name'))

    @api.constrains('x_room_start_date', 'x_room_return_date')
    def _check_x_room_dates(self):
        for line in self:
            if line.x_room_start_date and line.x_room_return_date:
                if line.x_room_return_date <= line.x_room_start_date:
                    raise ValidationError(
                        "La date de fin de séjour doit être postérieure à la date de début, "
                        f"pour la ligne « {line.product_id.name} »."
                    )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if line.x_is_a_room_offer and not line.x_room_start_date:
                line.x_room_start_date = line.start_date
                line.x_room_return_date = line.return_date
        return lines

    def _planning_slot_values(self):
        vals = super()._planning_slot_values()
        if self.is_rental and self.x_is_a_room_offer and self.x_room_start_date and self.x_room_return_date:
            vals.update(
                start_datetime=self.x_room_start_date,
                end_datetime=self.x_room_return_date,
            )
        return vals

    def _planning_slot_vals_list_per_sol(self):
        room_lines = self.filtered(
            lambda sol: sol.is_rental and sol.x_is_a_room_offer
            and sol.x_room_start_date and sol.x_room_return_date
        )
        other_lines = self - room_lines

        vals_list_per_sol = (
            super(SaleOrderLine, other_lines)._planning_slot_vals_list_per_sol()
            if other_lines else {}
        )

        problematic_services = []
        for sol in room_lines:
            role = sol.product_id.planning_role_id
            available_resources = role.resource_ids
            if not available_resources:
                problematic_services.append(sol.product_id.name)
                continue

            # Réutilise un slot déjà cliqué dans le Planning (flux "Nouvelle commande")
            orphan = self.env['planning.slot'].search([
                ('resource_id', 'in', available_resources.ids),
                ('sale_line_id', '=', False),
                ('start_datetime', '<=', sol.x_room_return_date),
                ('end_datetime', '>=', sol.x_room_start_date),
            ], order='id desc', limit=1)

            if orphan:
                orphan.write({
                    'sale_line_id': sol.id,
                    'sale_order_id': sol.order_id.id,
                    'state': 'published',
                    'start_datetime': sol.x_room_start_date,
                    'end_datetime': sol.x_room_return_date,
                })
                vals_list_per_sol[sol] = []
                continue

            # Disponibilité vérifiée sur la VRAIE période de la ligne, pas la période partagée
            unavailable_resource_slots = self.env['planning.slot'].search([
                ('resource_id', 'in', available_resources.ids),
                ('start_datetime', '<=', sol.x_room_return_date),
                ('end_datetime', '>=', sol.x_room_start_date),
            ])
            resource_leaves = self.env['resource.calendar.leaves'].search([
                ('resource_id', 'in', available_resources.ids),
                ('date_from', '<=', sol.x_room_return_date),
                ('date_to', '>=', sol.x_room_start_date),
            ])
            free_resources = available_resources - (
                unavailable_resource_slots.resource_id + resource_leaves.resource_id
            )

            if not free_resources:
                problematic_services.append(sol.product_id.name)
                continue

            vals = sol._planning_slot_values()
            vals['resource_id'] = free_resources[0].id
            vals_list_per_sol[sol] = [vals]

        if problematic_services:
            raise ValidationError(
                self.env._(
                    "Impossible de confirmer : aucune ressource disponible pour : %(problematic_services)s.",
                    problematic_services=problematic_services,
                )
            )

        return vals_list_per_sol


    @api.depends('x_room_start_date', 'x_room_return_date')
    def _compute_x_room_nights(self):
        for line in self:
            if line.x_room_start_date and line.x_room_return_date:
                delta = line.x_room_return_date - line.x_room_start_date
                line.x_room_nights = max(1, delta.days + (1 if delta.seconds else 0))
            else:
                line.x_room_nights = 0

    def _get_pricelist_price(self):
        if self.is_rental and self.x_is_a_room_offer and self.x_room_start_date and self.x_room_return_date:
            self.order_id._rental_set_dates()
            return self.order_id.pricelist_id._get_product_price(
                self.product_id.with_context(**self._get_product_price_context()),
                self.product_uom_qty or 1.0,
                currency=self.currency_id,
                uom=self.product_uom_id,
                date=self.order_id.date_order or fields.Date.today(),
                start_date=self.x_room_start_date,
                end_date=self.x_room_return_date,
            )
        return super()._get_pricelist_price()

    @api.onchange('x_room_start_date', 'x_room_return_date')
    def _onchange_x_room_dates_update_price(self):
        if self.is_rental and self.x_is_a_room_offer and self.x_room_start_date and self.x_room_return_date:
            self.price_unit = self._get_pricelist_price()