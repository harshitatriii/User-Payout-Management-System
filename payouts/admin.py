from django.contrib import admin

from .models import Creator, Brand, PayoutTransaction, Sale, Withdrawal

# Register your models here.

@admin.register(Creator)
class CreatorAdmin(admin.ModelAdmin):
    list_display = ["id", "username", "name", "balance", "created_at"]
    search_fields = ["username", "name"]

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["id", "name"]

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["id", "creator", "brand", "earning", "status", "advance_paid",
        "advance_amount", "reconciled_at",]
    list_filter = ["status", "advance_paid", "brand"]
    search_fields = ["creator__username"]

@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ["id", "creator", "amount", "status", "recovered", "created_at"]
    list_filter = ["status", "recovered"]


@admin.register(PayoutTransaction)
class PayoutTransactionAdmin(admin.ModelAdmin):
    list_display = ["id", "creator", "type", "amount", "sale", "withdrawal", "created_at"]
    list_filter = ["type"]
    search_fields = ["creator__username"]
