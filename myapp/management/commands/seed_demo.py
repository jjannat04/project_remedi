from django.core.management.base import BaseCommand

from myapp.services.demo_data import ensure_demo_users, get_demo_placeholders


class Command(BaseCommand):
    help = "Seed deterministic demo accounts and minimal demo placeholders."

    def handle(self, *args, **options):
        results = ensure_demo_users()

        self.stdout.write("Demo accounts:")
        for kind, (user, created) in results.items():
            action = "created" if created else "updated"
            self.stdout.write(
                f"- {action}: {kind} ({user.email}, role={user.role}, is_demo_account={user.is_demo_account})"
            )

        self.stdout.write("Demo placeholders:")
        for placeholder in get_demo_placeholders():
            self.stdout.write(f"- ready: {placeholder}")

        self.stdout.write(self.style.SUCCESS("Demo seed complete. No medicines, analytics, QR, OTP, or AI data created."))
