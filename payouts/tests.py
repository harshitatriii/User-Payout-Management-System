"""
Test suite. Proves the assignment's example end-to-end plus the key edge cases:
idempotency, reconciliation math, the 24h withdrawal limit, insufficient balance,
and failed-payout recovery.

Run: python manage.py test
"""
from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase

from .exceptions import (
    AlreadyReconciledError,
    InsufficientBalanceError,
    WithdrawalRateLimitError,
)
from .models import (
    Brand,
    Creator,
    PayoutTransaction,
    Sale,
    SaleStatus,
    TransactionType,
    WithdrawalStatus,
)
from .services import (
    AdvancePayoutService,
    LedgerService,
    PayoutRecoveryService,
    ReconciliationService,
    WithdrawalService,
)


class PayoutSystemTests(TestCase):
    def setUp(self):
        self.creator = Creator.objects.create(username="john_doe", name="John Doe")
        self.brand = Brand.objects.create(name="brand_1")
        self.sales = [
            Sale.objects.create(creator=self.creator, brand=self.brand, earning=Decimal("40.00"))
            for _ in range(3)
        ]

    # --- Advance payout ---

    def test_advance_payout_is_10_percent(self):
        result = AdvancePayoutService.run()
        self.creator.refresh_from_db()
        self.assertEqual(result["advances_paid"], 3)
        self.assertEqual(self.creator.balance, Decimal("12.00"))  # 10% of 120
        for sale in self.sales:
            sale.refresh_from_db()
            self.assertTrue(sale.advance_paid)
            self.assertEqual(sale.advance_amount, Decimal("4.00"))

    def test_advance_payout_is_idempotent(self):
        AdvancePayoutService.run()
        AdvancePayoutService.run()  # run again...
        AdvancePayoutService.run()  # ...and again
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.balance, Decimal("12.00"))  # still 12, no double pay
        self.assertEqual(
            PayoutTransaction.objects.filter(type=TransactionType.ADVANCE).count(), 3
        )

    # --- The full assignment example: final payout = Rs.68 ---

    def test_full_example_final_payout_is_68(self):
        AdvancePayoutService.run()  # advance 12 total (4 each)
        ReconciliationService.reconcile(self.sales[0].id, SaleStatus.REJECTED)  # -4
        ReconciliationService.reconcile(self.sales[1].id, SaleStatus.APPROVED)  # +36
        ReconciliationService.reconcile(self.sales[2].id, SaleStatus.APPROVED)  # +36

        self.creator.refresh_from_db()
        # Final settlement (after advances) = -4 + 36 + 36 = 68  (the assignment's answer)
        final_settlement = PayoutTransaction.objects.filter(
            creator=self.creator,
            type__in=[TransactionType.FINAL_CREDIT, TransactionType.CLAWBACK],
        ).aggregate(t=Sum("amount"))["t"]
        self.assertEqual(final_settlement, Decimal("68.00"))
        # Total balance = advance 12 + final 68 = 80 (= two approved sales x 40)
        self.assertEqual(self.creator.balance, Decimal("80.00"))
        # Cached balance matches the ledger source of truth.
        self.assertEqual(LedgerService.compute_balance(self.creator.id), Decimal("80.00"))

    def test_approved_sale_without_advance_pays_full_earning(self):
        # No advance job run; approving should credit the full earning.
        ReconciliationService.reconcile(self.sales[0].id, SaleStatus.APPROVED)
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.balance, Decimal("40.00"))

    def test_cannot_reconcile_twice(self):
        AdvancePayoutService.run()
        ReconciliationService.reconcile(self.sales[0].id, SaleStatus.APPROVED)
        with self.assertRaises(AlreadyReconciledError):
            ReconciliationService.reconcile(self.sales[0].id, SaleStatus.REJECTED)

    # --- Withdrawals ---

    def test_withdrawal_debits_balance_and_enforces_24h_limit(self):
        AdvancePayoutService.run()
        for sale in self.sales:
            ReconciliationService.reconcile(sale.id, SaleStatus.APPROVED)
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.balance, Decimal("120.00"))  # 12 + 3*36

        WithdrawalService.request_withdrawal(self.creator.id, Decimal("50.00"))
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.balance, Decimal("70.00"))

        # Second withdrawal within 24h is blocked.
        with self.assertRaises(WithdrawalRateLimitError):
            WithdrawalService.request_withdrawal(self.creator.id, Decimal("10.00"))

    def test_withdrawal_insufficient_balance(self):
        with self.assertRaises(InsufficientBalanceError):
            WithdrawalService.request_withdrawal(self.creator.id, Decimal("10.00"))  # balance 0

    # --- Failed payout recovery ---

    def test_failed_payout_is_recovered_and_retryable(self):
        AdvancePayoutService.run()
        for sale in self.sales:
            ReconciliationService.reconcile(sale.id, SaleStatus.APPROVED)

        withdrawal = WithdrawalService.request_withdrawal(self.creator.id, Decimal("50.00"))
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.balance, Decimal("70.00"))

        # Payment processor reports failure -> amount is credited back automatically.
        WithdrawalService.mark_status(withdrawal.id, WithdrawalStatus.FAILED)
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.balance, Decimal("120.00"))
        withdrawal.refresh_from_db()
        self.assertTrue(withdrawal.recovered)

        # Recovery is idempotent — calling it again does not double-credit.
        PayoutRecoveryService.recover(withdrawal.id)
        self.creator.refresh_from_db()
        self.assertEqual(self.creator.balance, Decimal("120.00"))

        # A failed payout does not count against the 24h limit -> user can retry now.
        retry = WithdrawalService.request_withdrawal(self.creator.id, Decimal("20.00"))
        self.assertEqual(retry.status, WithdrawalStatus.INITIATED)
