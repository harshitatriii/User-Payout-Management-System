from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .views import(
    BrandViewSet,
    CreatorViewSet,
    RunAdvancePayoutsView,
    SaleViewSet,
    WithdrawalViewSet
)

router = DefaultRouter()
router.register("creators", CreatorViewSet)
router.register("brands", BrandViewSet)
router.register("sales", SaleViewSet)
router.register("withdrawals", WithdrawalViewSet)

urlpatterns = [
    path("advance-payout/run/", RunAdvancePayoutsView.as_view(),
    name = "run-advance-payouts"),
    path("", include(router.urls))
]
