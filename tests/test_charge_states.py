from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestFolioChargeStates(TransactionCase):
    """Tests de caractérisation sur les transitions d'état d'une charge folio.

    ATTENTION : certains tests figent volontairement le comportement ACTUEL,
    y compris les trous comptables connus (X : annulation sans extourne,
    Y : remboursement sans contrepartie de revenu). Ils doivent passer au vert
    AVANT toute correction. Les assertions marquées TROU X / TROU Y seront
    modifiées délibérément lors de la correction.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        pm_model = cls.env["pos.payment.method"]
        pm_model._ensure_room_charge_method(cls.company)
        pm_model._ensure_extras_income_account(cls.company)
        pm_model._ensure_service_charge_account(cls.company)
        pm_model._ensure_service_income_account(cls.company)

        cls.acc_707200 = cls._get_account("707200")
        cls.acc_411200 = cls._get_account("411200")

        cls.partner = cls.env["res.partner"].create({"name": "Client Test Folio"})
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.partner.id,
            "company_id": cls.company.id,
        })

        journal = cls.env["account.journal"].search([
            ("type", "=", "cash"),
            ("company_id", "=", cls.company.id),
        ], limit=1)
        cls.assertTrue(journal, "Aucun journal de caisse trouvé sur la société.")
        cls.inbound_line = journal.inbound_payment_method_line_ids[:1]
        cls.outbound_line = journal.outbound_payment_method_line_ids[:1]

    @classmethod
    def _get_account(cls, code):
        return cls.env["account.account"].search([
            ("code", "=", code),
            ("company_ids", "in", cls.company.id),
        ], limit=1)

    def _create_due_charge(self, amount=50000.0, is_service=False):
        return self.env["pos.hotel.folio.charge"]._create_manual_charge({
            "name": "Charge de test",
            "sale_order_id": self.order.id,
            "partner_id": self.partner.id,
            "amount": amount,
            "payment_status": "due",
        }, is_service=is_service)

    def _cancel_wizard(self, charge):
        return self.env["pos.hotel.charge.cancel.wizard"].create({
            "charge_id": charge.id,
            "reason": "Motif de test",
        })

    def _revenue_balance(self, account):
        """Solde créditeur net du compte de revenu pour ce partenaire."""
        lines = self.env["account.move.line"].search([
            ("account_id", "=", account.id),
            ("partner_id", "=", self.partner.id),
            ("parent_state", "=", "posted"),
        ])
        return sum(lines.mapped("credit")) - sum(lines.mapped("debit"))

    # ------------------------------------------------------------------
    # Création
    # ------------------------------------------------------------------

    def test_manual_charge_posts_income_entry(self):
        charge = self._create_due_charge(amount=50000.0)
        self.assertEqual(charge.payment_status, "due")
        self.assertTrue(charge.x_manual_income_move_id)
        self.assertEqual(charge.x_manual_income_move_id.state, "posted")
        self.assertEqual(self._revenue_balance(self.acc_707200), 50000.0)

    # ------------------------------------------------------------------
    # Annulation
    # ------------------------------------------------------------------

    def test_cancel_due_charge_sets_cancelled(self):
        charge = self._create_due_charge()
        self._cancel_wizard(charge).action_confirm()
        self.assertEqual(charge.payment_status, "cancelled")

    def test_cancel_due_charge_leaves_revenue_posted(self):
        """TROU X — à corriger à l'étape 3 : le revenu doit tomber à 0."""
        charge = self._create_due_charge(amount=50000.0)
        self._cancel_wizard(charge).action_confirm()
        self.assertEqual(self._revenue_balance(self.acc_707200), 50000.0)

    def test_cancel_blocked_when_invoice_active(self):
        """Garde ajoutée à l'étape 1 — non-regression."""
        charge = self._create_due_charge(amount=50000.0)
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": fields.Date.context_today(charge),
            "invoice_line_ids": [Command.create({
                "name": "Ligne de test",
                "quantity": 1,
                "price_unit": 50000.0,
                "account_id": self.acc_707200.id,
            })],
        })
        invoice.action_post()
        charge.x_invoice_id = invoice
        self.assertTrue(charge.x_invoice_is_active)

        with self.assertRaises(UserError):
            charge.action_open_cancel_wizard()
        with self.assertRaises(UserError):
            self._cancel_wizard(charge).action_confirm()
        self.assertEqual(charge.payment_status, "due")

    # ------------------------------------------------------------------
    # Règlement / remboursement
    # ------------------------------------------------------------------

    def test_settle_then_refund_creates_mirror_charge(self):
        charge = self._create_due_charge(amount=50000.0)
        charge.action_settle(self.inbound_line.id)
        self.assertEqual(charge.payment_status, "settled")
        self.assertTrue(charge.settlement_payment_id)

        charge.action_refund_settled(self.outbound_line.id)
        self.assertEqual(charge.refund_status, "full")
        self.assertEqual(charge.amount_net, 0.0)
        self.assertEqual(len(charge.refund_charge_ids), 1)

    def test_refund_leaves_revenue_posted(self):
        """TROU Y — à corriger à l'étape 3 : le revenu doit tomber à 0."""
        charge = self._create_due_charge(amount=50000.0)
        charge.action_settle(self.inbound_line.id)
        charge.action_refund_settled(self.outbound_line.id)
        self.assertEqual(self._revenue_balance(self.acc_707200), 50000.0)