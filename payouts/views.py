from decimal import Decimal

from django.db.models import Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Brand, Creator, Sale, TransactionType, Withdrawal

from .services import (
    AdvancePayoutService,
    LedgerService,
    ReconciliationService,
    WithdrawalService,
)

from .serializers import (
    BrandSerializer,
    CreatorSerializer,
    MarkWithdrawalSerializer,
    PayoutTransactionSerializer,
    ReconcileInputSerializer,
    RunAdvanceSerializer,
    SaleSerializer,
    WithdrawalRequestSerializer,
    WithdrawalSerializer,
)

class CreatorViewSet(viewsets.ModelViewSet):
    queryset = Creator.objects.all().order_by("id")
    serializer_class = CreatorSerializer
    http_method_names = ["get", "post"]

    @action(detail=True, methods=["get"])
    def balance(self, request, pk=None):
        creator = self.get_object()
        return Response({
            "creator": creator.username,
            "cached_balance": creator.balance,
            "ledger_balance": LedgerService.compute_balance(creator.id),
        })

    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        creator = self.get_object()
        txns = creator.transactions.all().order_by("id")
        return Response(PayoutTransactionSerializer(txns, many=True).data)


    @action(detail=True, methods=["get"], url_path="payout-summary")
    def payout_summary(self, request, pk=None):
        """Human-friendly breakdown that mirrors the assignment's framing."""
        creator = self.get_object()
        txns = creator.transactions.all()

        def total(*types):
            return txns.filter(type__in=types).aggregate(t=Sum("amount"))["t"] or Decimal("0.00")

        return Response({
            "creator": creator.username,
            "advance_paid_total": total(TransactionType.ADVANCE),
            # Final settlement after advances = the assignment's "Final Payout".
            "final_settlement_total": total(
                TransactionType.FINAL_CREDIT, TransactionType.CLAWBACK
            ),
            "withdrawn_total": total(TransactionType.WITHDRAWAL_DEBIT),
            "recovered_total": total(TransactionType.RECOVERY_CREDIT),
            "current_balance": creator.balance,
        })


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all().order_by("id")
    serializer_class = BrandSerializer
    http_method_names = ["get", "post"]


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all().order_by("id")
    serializer_class = SaleSerializer
    http_method_names = ["get", "post"]

    def get_queryset(self):
        qs = super().get_queryset()
        creator_id = self.request.query_params.get("creator")
        sale_status = self.request.query_params.get("status")
        if creator_id:
            qs = qs.filter(creator_id=creator_id)
        if sale_status:
            qs = qs.filter(status=sale_status)
        return qs

    @action(detail=True, methods=["post"])
    def reconcile(self, request, pk=None):
        payload = ReconcileInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        sale = ReconciliationService.reconcile(int(pk), payload.validated_data["status"])
        return Response(SaleSerializer(sale).data)


class WithdrawalViewSet(viewsets.ModelViewSet):
    queryset = Withdrawal.objects.all().order_by("id")
    serializer_class = WithdrawalSerializer
    http_method_names = ["get", "post"]

    def create(self, request, *args, **kwargs):
        payload = WithdrawalRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        withdrawal = WithdrawalService.request_withdrawal(
            payload.validated_data["creator"], payload.validated_data["amount"]
        )
        return Response(
            WithdrawalSerializer(withdrawal).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def mark(self, request, pk=None):
        payload = MarkWithdrawalSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        withdrawal = WithdrawalService.mark_status(int(pk), payload.validated_data["status"])
        return Response(WithdrawalSerializer(withdrawal).data)


class RunAdvancePayoutsView(APIView):
    """POST /api/advance-payouts/run/  -> runs the advance job (optionally per creator)."""

    def post(self, request):
        payload = RunAdvanceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = AdvancePayoutService.run(payload.validated_data.get("creator"))
        return Response(result)

