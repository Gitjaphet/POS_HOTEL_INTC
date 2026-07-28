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

    def _planning_slot_vals_list_per_sol(self):
        vals_list_per_sol = super()._planning_slot_vals_list_per_sol()
        for sol, vals_list in vals_list_per_sol.items():
            role = sol.product_id.planning_role_id
            if not (role.x_is_a_room_offer and vals_list):
                continue

            orphan = self.env['planning.slot'].search([
                ('resource_id', 'in', role.resource_ids.ids),
                ('sale_line_id', '=', False),
                ('start_datetime', '<=', sol.return_date),
                ('end_datetime', '>=', sol.start_date),
            ], order='id desc', limit=1)

            if orphan:
                orphan.write({
                    'sale_line_id': sol.id,
                    'sale_order_id': sol.order_id.id,
                    'state': 'published',
                })
                vals_list_per_sol[sol] = []

        return vals_list_per_sol