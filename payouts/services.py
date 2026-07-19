#Service Layer - all payout business logic is here

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from .constants import ADVANCE_RATE, MONEY_QUANTIZE, WITHDRAWAL_COOLDOWN_HOURS

from .exceptions import (
    AlreadyReconciledError,
    InsufficientBalanceError,
    InvalidAmountError,
    InvalidReconcileStatusError,
    WithdrawalRateLimitError,
)

from .models import (
    Creator,
    PayoutTransaction,
    Sale,
    SaleStatus,
    TransactionType,
    Withdrawal,
    WithdrawalStatus,
)

def money(value) -> Decimal:
    # returns money quantized to 2 decimal places
    return Decimal(value).quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def _post(creator, txn_type, amount, *, sale=None,withdrawal=None, description=""):
    #Add a ledger entry in PayoutTransaction table and update creator.balance
    #always call inside an atomic block with creator row locked.

    PayoutTransaction.objects.create(
        creator=creator,
        sale=sale,
        withdrawal=withdrawal,
        type=txn_type,
        amount=amount,
        description=description,
    )

    creator.balance = money(creator.balance + amount)
    creator.save(update_fields=["balance"])

class LedgerService:

    def compute_balance(creator_id: int) -> Decimal:
        #calculate balance from ledgers for audit.
        total = PayoutTransaction.objects.filter(creator_id=creator_id).aggregate(total=Sum("amount"))["total"]
        return money(total or Decimal("0.00"))

class AdvancePayoutService:
    #Pays a one time advance amt 10% on pedning sales, Idempotently

    Rate = ADVANCE_RATE

    @classmethod
    def compute_advance(cls, earning: Decimal) -> Decimal:
        return money(earning * cls.Rate)

    @classmethod
    @transaction.atomic
    def pay_advance_for_sale(cls, sale_id: int) -> bool:
        #Pay advance for a single sale
        # Returns True if paid, else False

        sale = Sale.objects.select_for_update().get(pk=sale_id)
        if sale.status != SaleStatus.PENDING or sale.advance_paid:
            return False

        creator = Creator.objects.select_for_update().get(pk = sale.creator_id)
        advance = cls.compute_advance(sale.earning)
        _post(
            creator,
            TransactionType.ADVANCE,
            advance,
            sale=sale,
            description=f"Advance 10% for sale #{sale.pk}",
        )
        sale.advance_paid = True
        sale.advance_amount = advance
        sale.save(update_fields=["advance_paid", "advance_amount"])
        return True

    @classmethod
    def run(cls, creator_id:int | None = None) -> dict:
        #Run advance payout job for all eligible pending sales.

        qs = Sale.objects.filter(status=SaleStatus.PENDING, advance_paid=False)
        if creator_id is not None:
            qs = qs.filter(creator_id=creator_id)

        sale_ids = list(qs.values_list("id", flat=True))
        paid = 0
        for sid in sale_ids:
            try:
                if cls.pay_advance_for_sale(sid):
                    paid += 1
            except IntegrityError:
                #concurrent run already advanced this sale
                continue
        return {
            "eligible_sales" : len(sale_ids),
            "advances_paid" : paid 
            }
        


class ReconciliationService:
    """Admin reconciles a pending sale to approved/rejected and settles the payout."""

    @staticmethod
    @transaction.atomic
    def reconcile(sale_id: int, new_status: str) -> Sale:
        if new_status not in (SaleStatus.APPROVED, SaleStatus.REJECTED):
            raise InvalidReconcileStatusError(new_status)

        sale = Sale.objects.select_for_update().get(pk=sale_id)
        if sale.status != SaleStatus.PENDING:
            # State machine: a sale can only be reconciled once.
            raise AlreadyReconciledError(sale.pk, sale.status)

        creator = Creator.objects.select_for_update().get(pk=sale.creator_id)
        advance = sale.advance_amount

        if new_status == SaleStatus.APPROVED:
            # Approved: user keeps full earning
            # pay earning - advance
            final_credit = money(sale.earning - advance)
            _post(
                creator,
                TransactionType.FINAL_CREDIT,
                final_credit,
                sale=sale,
                description=(
                    f"Final payout for approved sale #{sale.pk} "
                    f"(earning {sale.earning} - advance {advance})"
                ),
            )
        else:  # REJECTED
            # Rejected: the advance was not earned -> claw it back.
            clawback = money(advance)
            if clawback > 0:
                _post(
                    creator,
                    TransactionType.CLAWBACK,
                    -clawback,
                    sale=sale,
                    description=f"Clawback of advance for rejected sale #{sale.pk}",
                )

        sale.status = new_status
        sale.reconciled_at = timezone.now()
        sale.save(update_fields=["status", "reconciled_at"])
        return sale


class WithdrawalService:
    """Handles withdrawal requests, the 24h limit, and status transitions."""

    COOLDOWN = timedelta(hours=WITHDRAWAL_COOLDOWN_HOURS)
    # Statuses that count against the 24h limit. Failed/cancelled/rejected do NOT,
    # so a user whose payout failed can retry immediately (PayoutRecoveryService).
    BLOCKING_STATUSES = [
        WithdrawalStatus.INITIATED,
        WithdrawalStatus.PROCESSING,
        WithdrawalStatus.SUCCESS,
    ]

    @classmethod
    @transaction.atomic
    def request_withdrawal(cls, creator_id: int, amount) -> Withdrawal:
        amount = money(amount)
        if amount <= 0:
            raise InvalidAmountError(amount)

        creator = Creator.objects.select_for_update().get(pk=creator_id)

        since = timezone.now() - cls.COOLDOWN
        has_recent = Withdrawal.objects.filter(
            creator=creator, created_at__gte=since, status__in=cls.BLOCKING_STATUSES
        ).exists()
        if has_recent:
            raise WithdrawalRateLimitError()

        if amount > creator.balance:
            raise InsufficientBalanceError(amount, creator.balance)

        withdrawal = Withdrawal.objects.create(
            creator=creator, amount=amount, status=WithdrawalStatus.INITIATED
        )
        _post(
            creator,
            TransactionType.WITHDRAWAL_DEBIT,
            -amount,
            withdrawal=withdrawal,
            description=f"Withdrawal #{withdrawal.pk} initiated",
        )
        return withdrawal

    @staticmethod
    @transaction.atomic
    def mark_status(withdrawal_id: int, new_status: str) -> Withdrawal:
        """
        Simulate the payment processor's callback. On a terminal failure the amount is
        automatically recovered back to the creator's balance.
        """
        withdrawal = Withdrawal.objects.select_for_update().get(pk=withdrawal_id)
        withdrawal.status = new_status
        if new_status in (
            WithdrawalStatus.SUCCESS,
            WithdrawalStatus.FAILED,
            WithdrawalStatus.CANCELLED,
            WithdrawalStatus.REJECTED,
        ):
            withdrawal.completed_at = timezone.now()
        withdrawal.save(update_fields=["status", "completed_at"])

        if new_status in PayoutRecoveryService.RECOVERABLE:
            PayoutRecoveryService.recover(withdrawal.pk)
        return withdrawal


class PayoutRecoveryService:
    """Credits a failed/cancelled/rejected payout back to the creator's balance."""

    RECOVERABLE = [
        WithdrawalStatus.FAILED,
        WithdrawalStatus.CANCELLED,
        WithdrawalStatus.REJECTED,
    ]

    @classmethod
    @transaction.atomic
    def recover(cls, withdrawal_id: int) -> bool:
        """Idempotent: credits the amount back at most once (guarded by ``recovered``)."""
        withdrawal = Withdrawal.objects.select_for_update().get(pk=withdrawal_id)
        if withdrawal.status not in cls.RECOVERABLE or withdrawal.recovered:
            return False

        creator = Creator.objects.select_for_update().get(pk=withdrawal.creator_id)
        _post(
            creator,
            TransactionType.RECOVERY_CREDIT,
            withdrawal.amount,
            withdrawal=withdrawal,
            description=f"Recovery credit for failed withdrawal #{withdrawal.pk}",
        )
        withdrawal.recovered = True
        withdrawal.save(update_fields=["recovered"])
        return True

