from rest_framework import serializers

from .models import Brand, Creator, PayoutTransaction, Sale, Withdrawal

class CreatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Creator
        fields = ["id", "username", "name", "balance", "created_at"]
        read_only_fields = ["balance", "created_at"]

class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name"]


class SaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sale
        fields = [
            "id", "creator", "brand", "earning", "status",
            "advance_paid", "advance_amount", "reconciled_at", "created_at",
        ]
        # Status/advance are driven by the services, never set directly via the API.
        read_only_fields = [
            "status", "advance_paid", "advance_amount", "reconciled_at", "created_at",
        ]

    def validate_earning(self, value):
        if value <= 0:
            raise serializers.ValidationError("Earning must be greater than 0.")
        return value


class PayoutTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutTransaction
        fields = [
            "id", "creator", "sale", "withdrawal", "type", "amount",
            "description", "created_at",
        ]


class WithdrawalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Withdrawal
        fields = [
            "id", "creator", "amount", "status", "recovered",
            "created_at", "completed_at",
        ]
        read_only_fields = ["status", "recovered", "created_at", "completed_at"]


# --- Input-only serializers for custom actions ---

class ReconcileInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["approved", "rejected"])


class WithdrawalRequestSerializer(serializers.Serializer):
    creator = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class MarkWithdrawalSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["processing", "success", "failed", "cancelled", "rejected"]
    )


class RunAdvanceSerializer(serializers.Serializer):
    creator = serializers.IntegerField(required=False)
