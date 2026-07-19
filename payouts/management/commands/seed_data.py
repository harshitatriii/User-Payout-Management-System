"""
Seed the exact example from the assignment so the reviewer can reproduce it instantly:

    python manage.py seed_data
    python manage.py run_advance_payouts       # advance = Rs.12 (4+4+4)
    # then reconcile 1 rejected + 2 approved (via API or admin) -> final settlement Rs.68
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from payouts.models import Brand, Creator, Sale


class Command(BaseCommand):
    help = "Seed sample data (john_doe with 3 pending sales of Rs.40) from the assignment."

    def handle(self, *args, **options):
        creator, _ = Creator.objects.get_or_create(
            username="john_doe", defaults={"name": "John Doe"}
        )
        for name in ("brand_1", "brand_2", "brand_3"):
            Brand.objects.get_or_create(name=name)
        brand_1 = Brand.objects.get(name="brand_1")

        for _ in range(3):
            Sale.objects.create(creator=creator, brand=brand_1, earning=Decimal("40.00"))

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded creator 'john_doe' with 3 pending sales of Rs.40.00 each "
                "(total pending earnings Rs.120)."
            )
        )
