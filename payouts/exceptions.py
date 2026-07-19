from django.core.exceptions import ObjectDoesNotExist
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

class PayoutError(Exception):
    #Base class for all payout related errors
    status_code = 400

    def __init__(self, message):
        self.message = message
        super().__init__(message)

class AlreadyReconciledError(PayoutError):
    status_code = 409 #conflict

    def __init__(self, sale_id, status):
        super().__init__(f"Sale #{sale_id} is already reconciled (status={status}).")

class InvalidReconcileStatusError(PayoutError):
    status_code = 400

    def __init__(self, status):
        super().__init__(
            f"Invalid reconcile status '{status}'. Must be 'approved' or 'rejected'."
        )


class WithdrawalRateLimitError(PayoutError):
    status_code = 429  # Too Many Requests

    def __init__(self):
        super().__init__("Only one withdrawal is allowed every 24 hours.")


class InsufficientBalanceError(PayoutError):
    status_code = 400

    def __init__(self, amount, balance):
        super().__init__(
            f"Insufficient balance: requested {amount}, available {balance}."
        )


class InvalidAmountError(PayoutError):
    status_code = 400

    def __init__(self, amount):
        super().__init__(f"Invalid amount: {amount}. Must be greater than 0.")


def drf_exception_handler(exc, context):
    """Map domain errors + missing objects to proper HTTP responses."""
    if isinstance(exc, PayoutError):
        return Response({"error": exc.message}, status=exc.status_code)
    if isinstance(exc, ObjectDoesNotExist):
        return Response({"error": "Resource not found."}, status=404)
    return drf_default_handler(exc, context)
 