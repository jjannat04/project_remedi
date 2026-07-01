from django.core.management.base import BaseCommand

from myapp.services.demo_data import seed_demo_dataset


class Command(BaseCommand):
    help = "Seed deterministic demo accounts, medicines, and analytics foundation."

    def handle(self, *args, **options):
        dataset = seed_demo_dataset()

        self.stdout.write("Demo accounts:")
        for kind, (user, created) in dataset["users"].items():
            action = "created" if created else "updated"
            self.stdout.write(
                f"- {action}: {kind} ({user.email}, role={user.role}, is_demo_account={user.is_demo_account})"
            )

        self.stdout.write("Demo medicines:")
        for kind, (medicine, created) in dataset["medicines"].items():
            action = "created" if created else "updated"
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

        self.stdout.write(self.style.SUCCESS("Demo seed complete. No AI, OCR, QR generation, OTP, uploads, or external services used."))
