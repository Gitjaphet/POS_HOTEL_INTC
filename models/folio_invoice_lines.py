from odoo import fields, models
from odoo.fields import Command


class PosHotelFolioCharge(models.Model):
    """Lignes de facture des consommations, partagées par « Créer une
    facture » (avec la chambre) et « Facturer au client » (sans la chambre).

    Sections « Extras » (sous-sections « Restaurant / Bar » et « Ajoutés par
    l'hôtel ») et « Services ». Présentation détaillée (une ligne par
    consommation, avec sa date et le détail des formules) ou récapitulative
    (consommations du POS regroupées par ticket). La comptabilité
    (compensation, « Réglé pendant le séjour ») est passée à la confirmation
    de la facture, pas ici (23/10/2026).
    """
    _inherit = "pos.hotel.folio.charge"

    def _x_payer(self):
        """Qui paie cette consommation : la personne choisie au POS (client
        du ticket), à défaut le client de la réservation."""
        self.ensure_one()
        return self.partner_id or self.sale_order_id.partner_id

    def _x_local_dt(self, dt, fmt):
        return fields.Datetime.context_timestamp(self, dt).strftime(fmt) if dt else ""

    def _x_invoice_label(self):
        self.ensure_one()
        label = f"{self._x_local_dt(self.date, '%d/%m')} — {self.name}"
        if self.x_combo_detail:
            label += "\n" + "\n".join(f"· {item}" for item in self.x_combo_detail.splitlines())
        return label

    def _x_invoice_line_commands(self, layout="detailed"):
        if not self:
            return []
        company_id = self[:1].company_id.id or self.env.company.id
        extras_income = self._x_find_account("707200", company_id, "Ventes extras chambre")
        services_income = self._x_find_account("707300", company_id, "Ventes services chambre")

        def _line(charge):
            return Command.create({
                "name": charge._x_invoice_label(),
                "quantity": 1.0,
                "price_unit": charge.amount_net,
                "account_id": (services_income if charge.is_service else extras_income).id,
            })

        def _ticket_lines(charges):
            commands = []
            for order in charges.pos_order_id.sorted("date_order"):
                order_charges = charges.filtered(lambda c: c.pos_order_id == order)
                commands.append(Command.create({
                    "name": (
                        f"{self._x_local_dt(order.date_order, '%d/%m %H:%M')} — "
                        f"Ticket {order.pos_reference} ({order.config_id.name})"
                    ),
                    "quantity": 1.0,
                    "price_unit": sum(order_charges.mapped("amount_net")),
                    "account_id": extras_income.id,
                }))
            return commands

        extras = self.filtered(lambda c: not c.is_service)
        services = self.filtered("is_service")
        extras_pos = extras.filtered("pos_order_id")
        extras_manual = extras - extras_pos
        commands = []
        if extras:
            commands.append(Command.create({"display_type": "line_section", "name": "Extras"}))
            if extras_pos:
                commands.append(Command.create({"display_type": "line_subsection", "name": "Restaurant / Bar"}))
                if layout == "summary":
                    commands += _ticket_lines(extras_pos)
                else:
                    commands += [_line(c) for c in extras_pos.sorted("date")]
            if extras_manual:
                commands.append(Command.create({"display_type": "line_subsection", "name": "Ajoutés par l'hôtel"}))
                commands += [_line(c) for c in extras_manual.sorted("date")]
        if services:
            commands.append(Command.create({"display_type": "line_section", "name": "Services"}))
            commands += [_line(c) for c in services.sorted("date")]
        return commands
