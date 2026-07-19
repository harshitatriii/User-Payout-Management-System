"""
Advance-payout job as a management command.

    python manage.py run_advance_payouts            # all eligible pending sales
    python manage.py run_advance_payouts --creator 1

In production this would be scheduled (cron / Celery beat). It is idempotent, so
running it repeatedly never double-pays a sale.
"""
from django.core.management.base import BaseCommand

from payouts.services import AdvancePayoutService


class Command(BaseCommand):
    help = "Pay the one-time 10% advance on all eligible pending sales (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--creator", type=int, default=None, help="Limit to one creator id.")

    def handle(self, *args, **options):
        result = AdvancePayoutService.run(options.get("creator"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Advance payout run complete: "
                f"{result['advances_paid']} paid / {result['eligible_sales']} eligible."
            )
        )
