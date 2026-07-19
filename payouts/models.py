"""
Data Model shcema for the FAYM user payout management System

Design summary:

"""
from django.db import models
from decimal import Decimal

class SaleStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"

class TransactionType(models.TextChoices):
    ADVANCE = "advance", "Advance Payout" #10%
    FINAL_CREDIT = "final_credit", "Final Payout" # earning - advance
    CLAWBACK = "clawback", "Advance Clawback" # -advance
    WITHDRAWAL_DEBIT = "withdrawal_debit", "withdrawal" #-amount
    RECOVERY_CREDIT = "recovery_credit", "Failed Payout Recovery" # + amount back

class WithdrawalStatus(models.TextChoices):
    INITIATED = "initiated", "Initiated"
    PROCESSING = "processing", "Processing"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REJECTED = "rejected", "Rejected"


# actual models from here:

class Creator(models.Model):
    #creator who earns commissions
    username = models.CharField(max_length=150, unique=True)
    name = models.CharField(max_length=200, blank=True)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username

    
class Brand(models.Model):
    #A brand whose products creators promote

    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name


class Sale(models.Model):
    # An affiliate Sale:

    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name="sales")
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="sales")
    earning = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=SaleStatus.choices, default=SaleStatus.PENDING)
    advance_paid = models.BooleanField(default=False)
    advance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    reconciled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["creator", "status"]),
            models.Index(fields=["status", "advance_paid"]),
        ]

    def __str__(self):
        return f"Sale#{self.pk} {self.creator_id} {self.earning} {self.status}"

    
class Withdrawal(models.Model):
    #creators request to withdraw balance to their bank / upi
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name="withdrawals")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=WithdrawalStatus.choices, default=WithdrawalStatus.INITIATED
    )
    # Guards failed-payout recovery so the amount is credited back at most once.
    recovered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["creator", "created_at"]),
        ]

    def __str__(self):
        return f"Withdrawal#{self.pk} {self.creator_id} {self.amount} {self.status}"

class PayoutTransaction(models.Model):
    # Ledger Entries
    # Sum of creators transaction = balance

    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name="transactions")

    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, null=True, blank=True, related_name="transactions"
    )
    withdrawal = models.ForeignKey(
        Withdrawal, on_delete=models.CASCADE, null=True, blank=True, related_name="transactions"
    )
    type = models.CharField(max_length=30, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # IDEMPOTENCY GUARANTEE: at most one transaction of a given type per sale.
            # This is what makes a sale physically unable to receive two advances,
            # even if the advance-payout job runs concurrently or repeatedly.
            models.UniqueConstraint(
                fields=["sale", "type"],
                condition=models.Q(sale__isnull=False),
                name="uniq_sale_transaction_type",
            ),
        ]
        indexes = [
            models.Index(fields=["creator", "created_at"]),
        ]

    def __str__(self):
        return f"Txn#{self.pk} {self.creator_id} {self.type} {self.amount}"




