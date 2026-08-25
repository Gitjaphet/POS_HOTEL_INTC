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


    def _get_sale_order_line_multiline_description_sale(self):
        res = super()._get_sale_order_line_multiline_description_sale()
        if self.x_is_a_room_offer and self.x_room_resource_ids:
            room_word = "Chambre" if len(self.x_room_resource_ids) == 1 else "Chambres"
            room_names = ", ".join(self.x_room_resource_ids.mapped("name"))
            nights_word = "nuit" if self.x_room_nights == 1 else "nuits"
            res += f"\n{room_word} {room_names} — {self.x_room_nights} {nights_word}"
        return res

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
                # Écriture UNIQUE des deux dates, et sous x_syncing_room_dates :
                # deux assignations séparées déclencheraient chacune notre write(),
                # et la première pousserait return_date=False (pas encore assigné)
                # sur order.rental_return_date — écrasant la date de fin venue du
                # Planning. La garde de contexte empêche toute rétro-écriture vers
                # la commande : ici les champs natifs sont la source, pas la cible.
                line.with_context(x_syncing_room_dates=True).write({
                    'x_room_start_date': line.start_date,
                    'x_room_return_date': line.return_date,
                })
        room_lines = lines.filtered(lambda sol: sol.x_is_a_room_offer)
        room_lines._notify_room_occupancy_change()
        if room_lines:
            # Le texte de description doit refléter les dates chambre posées
            # juste au-dessus — l'écriture sous x_syncing_room_dates ne passe pas
            # par le recalcul du write(), sinon il resterait à "0 nuits".
            self.env.add_to_compute(
                self.env['sale.order.line']._fields['name'], room_lines
            )
        return lines
    
    def write(self, vals):
        room_lines_needing_sync = self.env['sale.order.line']
        if not self.env.context.get('x_syncing_room_dates') and (
            'start_date' in vals or 'return_date' in vals
            or 'x_room_start_date' in vals or 'x_room_return_date' in vals
        ):
            room_lines_needing_sync = self.filtered('x_is_a_room_offer')

        lines_to_check = self.env['sale.order.line']
        if 'product_uom_qty' in vals:
            lines_to_check = self.filtered(
                lambda sol: sol.is_rental and sol.x_is_a_room_offer and sol.order_id.state == 'sale'
            )

        # Garde symétrique de celle du bloc room_lines_needing_sync ci-dessus :
        # sous x_syncing_room_dates, l'écriture est une synchro interne dont les
        # slots sont déjà (ou vont être) la source — redescendre vers eux
        # relancerait la cascade et pourrait écraser des slots portant des
        # valeurs distinctes (cas multi-chambres).
        lines_to_sync_dates = self.env['sale.order.line']
        if not self.env.context.get('x_syncing_room_dates') and (
            'x_room_start_date' in vals or 'x_room_return_date' in vals
        ):
            lines_to_sync_dates = self.filtered(
                lambda sol: sol.is_rental and sol.x_is_a_room_offer
                and sol.order_id.state == 'sale' and sol.planning_slot_ids
            )

        lines_to_notify_occupancy = self.env['sale.order.line']
        if 'qty_delivered' in vals or 'qty_returned' in vals or 'x_room_start_date' in vals or 'x_room_return_date' in vals:
            lines_to_notify_occupancy = self.filtered(lambda sol: sol.x_is_a_room_offer)

        res = super().write(vals)

        if room_lines_needing_sync:
            if 'x_room_start_date' in vals or 'x_room_return_date' in vals:
                # Sens ligne → commande. rental_start_date/rental_return_date sont
                # des champs D'AGRÉGAT au niveau commande : ils doivent porter le
                # min/max de TOUTES les lignes chambre, jamais les dates de la seule
                # ligne éditée (sinon une chambre courte ramènerait la commande
                # entière à sa propre date).
                # slots_rescheduled=True bride le mécanisme natif
                # (sale_renting_planning/models/sale_order.py::write) qui, à chaque
                # changement de rental_*, repousse la nouvelle valeur sur TOUS les
                # slots alignés sur l'ancienne — ce qui écrase les chambres aux
                # périodes distinctes. Nos propres slots sont déjà synchronisés par
                # _sync_existing_room_slots_dates().
                for order in room_lines_needing_sync.order_id:
                    room_lines = order.order_line.filtered(
                        lambda sol: sol.x_is_a_room_offer
                        and sol.x_room_start_date and sol.x_room_return_date
                    )
                    if not room_lines:
                        continue
                    order.with_context(slots_rescheduled=True).write({
                        'rental_start_date': min(room_lines.mapped('x_room_start_date')),
                        'rental_return_date': max(room_lines.mapped('x_room_return_date')),
                    })
            else:
                # Sens commande → ligne (les champs natifs ont bougé) : on recopie
                # tel quel, en une seule écriture (cf. le commentaire de create()).
                for line in room_lines_needing_sync:
                    line.with_context(x_syncing_room_dates=True).write({
                        'x_room_start_date': line.start_date,
                        'x_room_return_date': line.return_date,
                    })

        if lines_to_check:
            lines_to_check._generate_missing_room_slots(
                forced_resource_id=self.env.context.get('x_forced_room_resource_id')
            )
        if lines_to_sync_dates:
            lines_to_sync_dates._sync_existing_room_slots_dates()
        if lines_to_notify_occupancy:
            lines_to_notify_occupancy._notify_room_occupancy_change()

        # Le texte de description (n° chambre + nuits + dates) doit suivre tout
        # changement de dates chambre, y compris quand _sync_existing_room_slots_dates
        # n'est pas appelé (commande encore en devis, ou sans planning.slot) — sinon
        # il reste figé sur une valeur périmée.
        if 'x_room_start_date' in vals or 'x_room_return_date' in vals:
            room_lines = self.filtered('x_is_a_room_offer')
            if room_lines:
                self.env.add_to_compute(
                    self.env['sale.order.line']._fields['name'], room_lines
                )

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
            sol.planning_slot_ids.with_context(rental_order_updated=True).write({
                'start_datetime': sol.x_room_start_date,
                'end_datetime': sol.x_room_return_date,
                'allocated_hours': allocated_hours,
                'allocated_percentage': 100,
            })
        # Le mécanisme natif qui mettrait le champ 'name' en file de recalcul
        # (sale_renting_planning/models/planning_slot.py::write(), normalement
        # déclenché quand un planning.slot est reprogrammé) est volontairement
        # court-circuité ci-dessus par notre contexte rental_order_updated=True
        # (pour empêcher l'écrasement des dates par le recalcul natif min/max
        # de tous les créneaux). Effet de bord : le texte de description
        # (numéro de chambre + nuits + dates) n'est alors jamais remis en file
        # de recalcul. On le fait nous-mêmes explicitement ici.
        self.env.add_to_compute(self.env['sale.order.line']._fields['name'], self)


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
            needed = int(sol.product_uom_qty) - len(sol.planning_slot_ids)
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

    def action_open_remove_room_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Retirer une chambre",
            'res_model': 'pos.hotel.remove.room.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_line_id': self.id,
            },
        }

    def action_remove_room(self, resource_id, reason, cancel_due_debt=False,
                            refund_settled_charges=False, refund_payment_method_line_id=False):
        self.ensure_one()
        slot = self.planning_slot_ids.filtered(lambda s: s.resource_id.id == resource_id)
        if not slot:
            raise ValidationError("Cette chambre n'est pas liée à cette ligne.")

        folio_charge = self.env['pos.hotel.folio.charge']
        ambiguous = folio_charge.search([
            ('sale_order_line_id', '=', self.id),
            ('x_room_resource_id', '=', False),
        ])
        if ambiguous:
            raise ValidationError(
                "Impossible de retirer cette chambre : des consommations liées à cette ligne "
                "ne sont pas rattachées à une chambre précise (données ambiguës). "
                "Vérifiez ces charges manuellement avant de continuer."
            )

        charges = folio_charge.search([
            ('sale_order_line_id', '=', self.id),
            ('x_room_resource_id', '=', resource_id),
            ('is_refund', '=', False),
        ])

        invoiced_charges = charges.filtered(
            lambda c: c.x_invoice_is_active
        )
        if invoiced_charges:
            invoice_names = ', '.join(
                (inv.name or "Brouillon") for inv in invoiced_charges.mapped('x_invoice_id')
            )
            raise ValidationError(
                f"Cette chambre a des extras déjà inclus dans une facture non annulée "
                f"({invoice_names}). Annulez d'abord cette facture (ou établissez un avoir) "
                "avant de retirer la chambre."
            )
        
        paid_charges = charges.filtered(
            lambda c: c.payment_status == 'paid_pos' and not c.currency_id.is_zero(c.amount_net)
        )

        if paid_charges:
            raise ValidationError(
                "Cette chambre a des extras payés au POS non remboursés. "
                "Effectuez d'abord le remboursement via le POS avant de retirer la chambre."
            )
        settled_charges = charges.filtered(
            lambda c: c.payment_status == 'settled' and not c.currency_id.is_zero(c.amount_net)
        )
        if settled_charges and not refund_settled_charges:
            raise ValidationError(
                "Cette chambre a des extras ou services réglés à rembourser. "
                "Cochez le remboursement dans le wizard pour continuer."
            )
        if settled_charges and refund_settled_charges:
            if not refund_payment_method_line_id:
                raise ValidationError(
                    "Un mode de paiement pour le remboursement est requis."
                )
            for is_service in set(settled_charges.mapped('is_service')):
                settled_charges.filtered(
                    lambda c, v=is_service: c.is_service == v
                ).action_refund_settled(refund_payment_method_line_id)

        due_charges = charges.filtered(
            lambda c: c.payment_status == 'due' and not c.x_invoice_is_active
        )
        if due_charges and cancel_due_debt:
            due_charges._transition_to_cancelled(reason=reason)

        resource_name = slot.resource_id.name
        resource = slot.resource_id
        due_amount_at_removal = sum(due_charges.mapped('amount_net')) if due_charges else 0.0
        self.env['pos.hotel.room.removal.log'].create({
            'sale_order_id': self.order_id.id,
            'sale_order_line_id': self.id,
            'resource_id': resource.id,
            'resource_name': resource_name,
            'reason': reason,
            'cancel_due_debt': cancel_due_debt,
            'due_amount_at_removal': due_amount_at_removal,
        })
        slot.unlink()
        self.write({'product_uom_qty': self.product_uom_qty - 1})
        self.order_id.message_post(
            body=f"Chambre {resource_name} retirée de la ligne « {self.product_id.name} ». "
                f"Motif : {reason}"
                + (f" Dette annulée sur {len(due_charges)} charge(s)." if due_charges and cancel_due_debt else "")
        )
        self._notify_room_occupancy_change()

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


    def _adjust_room_stay_date(self, slot, edge, new_datetime):
        """Ajuste la date de début ou de fin de séjour d'une chambre précise
        (slot). Si la ligne regroupe plusieurs chambres, la chambre concernée
        est séparée dans sa propre ligne (même logique que action_remove_room)
        pour ne jamais impacter les autres chambres du groupe.
        Retourne la ligne (self ou une nouvelle ligne) portant désormais le slot.
        """
        self.ensure_one()
        if len(self.planning_slot_ids) <= 1:
            line = self
        else:
            was_delivered = 1 if slot.x_stay_status in ('checked_in', 'checked_out') else 0
            was_returned = 1 if slot.x_stay_status == 'checked_out' else 0
            line = self.with_context(planning_slot_generation=False).copy({
                'product_uom_qty': 1,
                'qty_delivered': was_delivered,
                'qty_returned': was_returned,
                'planning_slot_ids': [],
            })
            slot.write({
                'sale_line_id': line.id,
                'sale_order_id': line.order_id.id,
            })
            self.write({
                'product_uom_qty': self.product_uom_qty - 1,
                'qty_delivered': max(0, self.qty_delivered - was_delivered),
                'qty_returned': max(0, self.qty_returned - was_returned),
            })

        if edge == 'start':
            line.x_room_start_date = new_datetime
        else:
            line.x_room_return_date = new_datetime

        line.price_unit = line._get_pricelist_price()
        return line

    def _compute_product_updatable(self):
        super()._compute_product_updatable()
        for line in self:
            if (
                line.x_is_a_room_offer
                and line.state != 'cancel'
                and line.qty_delivered == 0
                and line.qty_invoiced == 0
            ):
                line.product_updatable = True




    