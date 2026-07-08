from django.core.management.base import BaseCommand

from myapp.services.demo_data import seed_demo_dataset


class Command(BaseCommand):
    help = "Seed deterministic demo accounts, medicines, reservations, QR codes, and analytics foundation."

    def handle(self, *args, **options):
        dataset = seed_demo_dataset()

        self.stdout.write("Demo accounts:")
        for kind, (user, created) in dataset["users"].items():
            action = "created" if created else "already exists, refreshed"
            self.stdout.write(
                f"- {action}: {kind} ({user.email}, role={user.role}, password=remedi4567)"
            )

        self.stdout.write("Demo pickup locations:")
        for _kind, (corner, created) in dataset["corners"].items():
            action = "created" if created else "already exists, refreshed"
            self.stdout.write(f"- {action}: {corner.name} ({corner.city})")

        self.stdout.write("Demo medicines:")
        for kind, (medicine, created) in dataset["medicines"].items():
            action = "created" if created else "already exists, refreshed"
            reserved = " reserved" if medicine.status == "verified" and medicine.patient_id else ""
            self.stdout.write(
                f"- {action}: {kind} ({medicine.name}, batch={medicine.batch_number}, status={medicine.status}{reserved})"
            )

        analytics = dataset["analytics"]
        self.stdout.write("Demo analytics:")
        self.stdout.write(f"- medicines donated: {analytics['medicines_donated']}")
        self.stdout.write(f"- medicines verified: {analytics['medicines_verified']}")
        self.stdout.write(f"- medicines rejected: {analytics['medicines_rejected']}")
        self.stdout.write(f"- medicines redistributed/sold: {analytics['medicines_redistributed']}")
        self.stdout.write(f"- estimated savings: {analytics['estimated_savings']} BDT")
        self.stdout.write(f"- waste prevented count: {analytics['waste_prevented_count']}")
        self.stdout.write(f"- patients helped count: {analytics['patients_helped_count']}")

        summary = dataset["summary"]
        self.stdout.write("Demo dataset summary:")
        self.stdout.write(f"- regular users: {summary['regular_users']}")
        self.stdout.write(f"- licensed pharmacists: {summary['pharmacists']}")
        self.stdout.write(f"- medicines: {summary['medicines']}")
        self.stdout.write(f"- marketplace listings: {summary['marketplace_listings']}")
        self.stdout.write(f"- reservations: {summary['reservations']}")
        self.stdout.write(f"- active reservations: {summary['active_reservations']}")
        self.stdout.write(f"- QR codes generated: {summary['qr_codes']}")
        self.stdout.write(f"- pickup locations: {summary['corners']}")

        self.stdout.write(self.style.SUCCESS("Demo seed complete. Safe to run again; existing demo rows are refreshed, not duplicated."))
