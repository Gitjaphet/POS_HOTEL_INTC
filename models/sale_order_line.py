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
    x_room_price_per_night = fields.Monetary(
        string="Prix / nuit",
        compute='_compute_x_room_price_per_night',
        currency_field='currency_id',
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

    @api.depends('x_room_start_date', 'x_room_return_date')
    def _compute_x_room_nights(self):
        for line in self:
            if line.x_room_start_date and line.x_room_return_date:
                delta = line.x_room_return_date - line.x_room_start_date
                line.x_room_nights = max(1, delta.days + (1 if delta.seconds else 0))
            else:
                line.x_room_nights = 0

    @api.depends('price_unit', 'x_room_nights')
    def _compute_x_room_price_per_night(self):
        for line in self:
            if line.x_is_a_room_offer and line.x_room_nights:
                line.x_room_price_per_night = line.price_unit / line.x_room_nights
            else:
                line.x_room_price_per_night = 0.0

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
        lines.filtered(lambda sol: sol.x_is_a_room_offer)._notify_room_occupancy_change()
        return lines
    
    def write(self, vals):
        lines_to_check = self.env['sale.order.line']
        if 'product_uom_qty' in vals:
            lines_to_check = self.filtered(
                lambda sol: sol.is_rental and sol.x_is_a_room_offer and sol.order_id.state == 'sale'
            )

        lines_to_sync_dates = self.env['sale.order.line']
        if 'x_room_start_date' in vals or 'x_room_return_date' in vals:
            lines_to_sync_dates = self.filtered(
                lambda sol: sol.is_rental and sol.x_is_a_room_offer
                and sol.order_id.state == 'sale' and sol.planning_slot_ids
            )

        lines_to_notify_occupancy = self.env['sale.order.line']
        if 'qty_delivered' in vals or 'qty_returned' in vals:
            lines_to_notify_occupancy = self.filtered(lambda sol: sol.x_is_a_room_offer)

        res = super().write(vals)

        if lines_to_check:
            lines_to_check._generate_missing_room_slots(
                forced_resource_id=self.env.context.get('x_forced_room_resource_id')
            )
        if lines_to_sync_dates:
            lines_to_sync_dates._sync_existing_room_slots_dates()
        if lines_to_notify_occupancy:
            lines_to_notify_occupancy._notify_room_occupancy_change()

        return res

    def _notify_room_occupancy_change(self):
        for line in self:
            sessions = self.env['pos.session'].search([
                ('state', '=', 'opened'),
                ('company_id', '=', line.company_id.id),
            ])
            for session in sessions:
                session.config_id._notify('ROOM_OCCUPANCY_UPDATED', {
                    'sale_order_line_id': line.id,
                })

    def _sync_existing_room_slots_dates(self):
        for sol in self:
            if not sol.x_room_start_date or not sol.x_room_return_date:
                continue
            allocated_hours = (
                sol.x_room_return_date - sol.x_room_start_date
            ).total_seconds() / 3600.0
            sol.planning_slot_ids.write({
                'start_datetime': sol.x_room_start_date,
                'end_datetime': sol.x_room_return_date,
                'allocated_hours': allocated_hours,
                'allocated_percentage': 100,
            })

    def _get_free_room_resources(self):
        """Ressources (chambres) du rôle produit de cette ligne, libres sur
        x_room_start_date/x_room_return_date, hors ressources déjà utilisées par la ligne."""
        self.ensure_one()
        role = self.product_id.planning_role_id
        available_resources = role.resource_ids
        if not available_resources or not self.x_room_start_date or not self.x_room_return_date:
            return self.env['resource.resource']

        already_used = self.planning_slot_ids.resource_id
        unavailable_resource_slots = self.env['planning.slot'].search([
            ('resource_id', 'in', available_resources.ids),
            ('sale_line_id', '!=', self.id),
            ('start_datetime', '<=', self.x_room_return_date),
            ('end_datetime', '>=', self.x_room_start_date),
        ])
        resource_leaves = self.env['resource.calendar.leaves'].search([
            ('resource_id', 'in', available_resources.ids),
            ('date_from', '<=', self.x_room_return_date),
            ('date_to', '>=', self.x_room_start_date),
        ])
        return available_resources - already_used - (
            unavailable_resource_slots.resource_id + resource_leaves.resource_id
        )

    def _generate_missing_room_slots(self, forced_resource_id=None):
        for sol in self:
            needed = max(1, int(sol.product_uom_qty)) - len(sol.planning_slot_ids)
            if needed <= 0 or not sol.x_room_start_date or not sol.x_room_return_date:
                continue

            free_resources = sol._get_free_room_resources()

            if forced_resource_id:
                resources_to_assign = free_resources.filtered(lambda r: r.id == forced_resource_id)
                if not resources_to_assign:
                    raise ValidationError(
                        self.env._(
                            "La chambre choisie n'est plus disponible sur cette période pour %(product_name)s.",
                            product_name=sol.product_id.name,
                        )
                    )
            else:
                if len(free_resources) < needed:
                    raise ValidationError(
                        self.env._(
                            "Impossible d'ajouter %(needed)s chambre(s) supplémentaire(s) pour %(product_name)s : "
                            "pas assez de ressources disponibles sur cette période.",
                            needed=needed, product_name=sol.product_id.name,
                        )
                    )
                resources_to_assign = free_resources[:needed]

            for resource in resources_to_assign:
                vals = sol._planning_slot_values()
                vals['resource_id'] = resource.id
                self.env['planning.slot'].create(vals)

    def action_open_add_room_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Ajouter une chambre",
            'res_model': 'pos.hotel.add.room.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_sale_order_line_id': self.id},
        }

    def _planning_slot_values(self):
        vals = super()._planning_slot_values()
        if self.is_rental and self.x_is_a_room_offer and self.x_room_start_date and self.x_room_return_date:
            allocated_hours = (
                self.x_room_return_date - self.x_room_start_date
            ).total_seconds() / 3600.0
            vals.update(
                start_datetime=self.x_room_start_date,
                end_datetime=self.x_room_return_date,
                allocated_hours=allocated_hours,
                allocated_percentage=100,
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

            unavailable_resource_slots = self.env['planning.slot'].search([
                ('resource_id', 'in', available_resources.ids),
                ('sale_line_id', '!=', False),
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

            nb_needed = max(1, int(sol.product_uom_qty))

            if len(free_resources) < nb_needed:
                problematic_services.append(sol.product_id.name)
                continue

            # Réutilise en priorité les slots orphelins déjà cliqués dans le Planning
            orphans = self.env['planning.slot'].search([
                ('resource_id', 'in', free_resources.ids),
                ('sale_line_id', '=', False),
                ('start_datetime', '<=', sol.x_room_return_date),
                ('end_datetime', '>=', sol.x_room_start_date),
            ])

            used_resource_ids = set()
            for orphan in orphans:
                if len(used_resource_ids) >= nb_needed:
                    break
                orphan.write({
                    'sale_line_id': sol.id,
                    'sale_order_id': sol.order_id.id,
                    'state': 'published',
                    'start_datetime': sol.x_room_start_date,
                    'end_datetime': sol.x_room_return_date,
                })
                used_resource_ids.add(orphan.resource_id.id)

            remaining_needed = nb_needed - len(used_resource_ids)
            remaining_resources = [
                r for r in free_resources if r.id not in used_resource_ids
            ][:remaining_needed]

            vals_list = []
            for resource in remaining_resources:
                vals = sol._planning_slot_values()
                vals['resource_id'] = resource.id
                vals_list.append(vals)

            vals_list_per_sol[sol] = vals_list

        if problematic_services:
            raise ValidationError(
                self.env._(
                    "Impossible de confirmer : aucune ressource disponible pour : %(problematic_services)s.",
                    problematic_services=problematic_services,
                )
            )

        return vals_list_per_sol

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