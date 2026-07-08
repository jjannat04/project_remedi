from django.core.management.base import BaseCommand

from myapp.services.demo_data import reset_demo_dataset


class Command(BaseCommand):
    help = "Delete demo-generated data, preserve superusers, and recreate the full demo dataset."

    def handle(self, *args, **options):
        dataset = reset_demo_dataset()
        deleted = dataset["deleted"]
        summary = dataset["summary"]

        self.stdout.write("Deleted demo data:")
        self.stdout.write(f"- medicines/reservations/QR state: {deleted['medicines']}")
        self.stdout.write(f"- regular users: {deleted['regular_users']}")
        self.stdout.write(f"- licensed pharmacists: {deleted['pharmacists']}")
        self.stdout.write(f"- pickup locations: {deleted['corners']}")
        self.stdout.write(f"- preserved superusers: {deleted['preserved_superusers']}")

        self.stdout.write("Recreated demo data:")
        self.stdout.write(f"- regular users: {summary['regular_users']}")
        self.stdout.write(f"- licensed pharmacists: {summary['pharmacists']}")
        self.stdout.write(f"- medicines: {summary['medicines']}")
        self.stdout.write(f"- marketplace listings: {summary['marketplace_listings']}")
        self.stdout.write(f"- reservations: {summary['reservations']}")
        self.stdout.write(f"- active reservations: {summary['active_reservations']}")
        self.stdout.write(f"- QR codes generated: {summary['qr_codes']}")
        self.stdout.write(f"- pickup locations: {summary['corners']}")

        self.stdout.write(self.style.SUCCESS("Demo reset complete. Superusers, schema, migrations, settings, and media directories were preserved."))
