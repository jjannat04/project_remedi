from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
import shutil
import tempfile
from io import BytesIO

from .models import Medicine, User
from .services.analytics import calculate_demo_analytics
from .services.demo_data import (
    DEMO_BATCH_PREFIX,
    DEMO_DONOR_EMAIL,
    DEMO_PATIENT_EMAIL,
    DEMO_PHARMACIST_EMAIL,
)


def create_test_image(name="package.png", size=(2200, 1400), color=(20, 120, 90)):
    from PIL import Image

    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo")
        call_command("seed_demo")

        donor = User.objects.get(email=DEMO_DONOR_EMAIL)
        pharmacist = User.objects.get(email=DEMO_PHARMACIST_EMAIL)
        patient = User.objects.get(email=DEMO_PATIENT_EMAIL)

        self.assertEqual(User.objects.filter(email=DEMO_DONOR_EMAIL).count(), 1)
        self.assertEqual(User.objects.filter(email=DEMO_PHARMACIST_EMAIL).count(), 1)
        self.assertEqual(User.objects.filter(email=DEMO_PATIENT_EMAIL).count(), 1)
        self.assertEqual(donor.role, User.Role.DONOR)
        self.assertEqual(pharmacist.role, User.Role.PHARMACIST)
        self.assertEqual(patient.role, User.Role.PATIENT)
        self.assertTrue(donor.is_demo_account)
        self.assertTrue(pharmacist.is_demo_account)
        self.assertTrue(patient.is_demo_account)
        self.assertTrue(pharmacist.is_active)

        demo_medicines = Medicine.objects.filter(batch_number__startswith=DEMO_BATCH_PREFIX)
        self.assertEqual(demo_medicines.count(), 7)
        self.assertEqual(demo_medicines.filter(status="pending").count(), 1)
        self.assertGreaterEqual(demo_medicines.filter(status="verified", patient__isnull=True).count(), 3)
        self.assertEqual(demo_medicines.filter(status="rejected").count(), 1)
        self.assertEqual(demo_medicines.filter(status="verified", patient=patient, completed_at__isnull=True).count(), 1)
        self.assertEqual(demo_medicines.filter(status="sold", patient=patient, completed_at__isnull=False).count(), 1)
        self.assertTrue(demo_medicines.filter(status="rejected").exclude(rejection_reason="").exists())

        analytics = calculate_demo_analytics()
        self.assertEqual(analytics["medicines_donated"], 7)
        self.assertEqual(analytics["medicines_rejected"], 1)
        self.assertEqual(analytics["medicines_redistributed"], 1)
        self.assertEqual(analytics["patients_helped_count"], 1)


class JudgeBypassTests(TestCase):
    @override_settings(DEMO_MODE=False)
    def test_judge_routes_are_not_available_when_demo_mode_off(self):
        self.assertEqual(self.client.get(reverse("judge_entry")).status_code, 404)
        response = self.client.post(reverse("judge_demo_login", args=["donor"]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(DEMO_MODE=True)
    def test_demo_donor_login_creates_session_and_redirects_to_profile(self):
        response = self.client.post(reverse("judge_demo_login", args=["donor"]))

        self.assertRedirects(response, reverse("profile"), fetch_redirect_response=False)
        user = User.objects.get(email=DEMO_DONOR_EMAIL)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)
        self.assertEqual(user.role, User.Role.DONOR)
        self.assertTrue(user.is_demo_account)

    @override_settings(DEMO_MODE=True)
    def test_demo_pharmacist_login_creates_session_and_redirects_to_dashboard(self):
        response = self.client.post(reverse("judge_demo_login", args=["pharmacist"]))

        self.assertRedirects(response, reverse("pharmacist_queue"), fetch_redirect_response=False)
        user = User.objects.get(email=DEMO_PHARMACIST_EMAIL)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)
        self.assertEqual(user.role, User.Role.PHARMACIST)
        self.assertTrue(user.is_demo_account)


class SeededDemoPageTests(TestCase):
    @override_settings(DEMO_MODE=True)
    def test_seeded_demo_pages_render(self):
        call_command("seed_demo")

        marketplace_response = self.client.get(reverse("marketplace"))
        self.assertEqual(marketplace_response.status_code, 200)
        self.assertContains(marketplace_response, "Available Medicines")
        self.assertContains(marketplace_response, "Reserved Demo Medicines")

        donor = User.objects.get(email=DEMO_DONOR_EMAIL)
        self.client.force_login(donor)
        profile_response = self.client.get(reverse("profile"))
        self.assertEqual(profile_response.status_code, 200)
        self.assertContains(profile_response, "Redistributed")
        self.assertContains(profile_response, "Outer strip seal is damaged")

        pharmacist = User.objects.get(email=DEMO_PHARMACIST_EMAIL)
        self.client.force_login(pharmacist)
        queue_response = self.client.get(reverse("pharmacist_queue"))
        self.assertEqual(queue_response.status_code, 200)
        self.assertContains(queue_response, "Verification Hub")
        self.assertContains(queue_response, "Napa 500 mg Tablet")


class MedicineImageUploadTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.donor = User.objects.create_user(
            username="image_donor",
            password="pass12345",
            role=User.Role.DONOR,
        )
        self.pharmacist = User.objects.create_user(
            username="image_pharmacist",
            password="pass12345",
            role=User.Role.PHARMACIST,
            is_active=True,
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def donation_payload(self, **overrides):
        payload = {
            "name": "Uploaded Medicine",
            "batch_number": "IMG-FOUNDATION-001",
            "expiry_date": "2028-05-20",
            "original_price": "500.00",
        }
        payload.update(overrides)
        return payload

    def test_donation_without_image_still_works(self):
        self.client.force_login(self.donor)

        response = self.client.post(reverse("donate_medicine"), self.donation_payload())

        self.assertRedirects(response, reverse("marketplace"), fetch_redirect_response=False)
        medicine = Medicine.objects.get(batch_number="IMG-FOUNDATION-001")
        self.assertEqual(medicine.donor, self.donor)
        self.assertFalse(medicine.medicine_image)

    def test_donation_with_image_compresses_and_stores_file(self):
        self.client.force_login(self.donor)

        response = self.client.post(
            reverse("donate_medicine"),
            self.donation_payload(
                batch_number="IMG-FOUNDATION-002",
                medicine_image=create_test_image(),
            ),
        )

        self.assertRedirects(response, reverse("marketplace"), fetch_redirect_response=False)
        medicine = Medicine.objects.get(batch_number="IMG-FOUNDATION-002")
        expected_prefix = timezone.now().strftime("medicines/%Y/%m/")
        self.assertTrue(medicine.medicine_image.name.startswith(expected_prefix))
        self.assertTrue(medicine.medicine_image.name.endswith(".jpg"))

        from PIL import Image

        with Image.open(medicine.medicine_image.path) as image:
            self.assertLessEqual(max(image.size), 1600)

    def test_profile_and_queue_render_image_thumbnail(self):
        self.client.force_login(self.donor)
        self.client.post(
            reverse("donate_medicine"),
            self.donation_payload(
                batch_number="IMG-FOUNDATION-003",
                medicine_image=create_test_image("queue-package.png", size=(900, 900)),
            ),
        )
        medicine = Medicine.objects.get(batch_number="IMG-FOUNDATION-003")

        profile_response = self.client.get(reverse("profile"))
        self.assertContains(profile_response, medicine.medicine_image.url)
        self.assertContains(profile_response, f'alt="{medicine.name} package"')

        self.client.force_login(self.pharmacist)
        queue_response = self.client.get(reverse("pharmacist_queue"))
        self.assertContains(queue_response, medicine.medicine_image.url)
        self.assertContains(queue_response, 'target="_blank"')

    def test_profile_renders_placeholder_without_image(self):
        Medicine.objects.create(
            donor=self.donor,
            name="No Image Medicine",
            batch_number="IMG-FOUNDATION-004",
            expiry_date="2028-06-15",
            original_price=Decimal("300.00"),
            status="pending",
        )
        self.client.force_login(self.donor)

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Image Medicine")
