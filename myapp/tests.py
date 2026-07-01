from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import User
from .services.demo_data import DEMO_DONOR_EMAIL, DEMO_PHARMACIST_EMAIL


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo")
        call_command("seed_demo")

        donor = User.objects.get(email=DEMO_DONOR_EMAIL)
        pharmacist = User.objects.get(email=DEMO_PHARMACIST_EMAIL)

        self.assertEqual(User.objects.filter(email=DEMO_DONOR_EMAIL).count(), 1)
        self.assertEqual(User.objects.filter(email=DEMO_PHARMACIST_EMAIL).count(), 1)
        self.assertEqual(donor.role, User.Role.DONOR)
        self.assertEqual(pharmacist.role, User.Role.PHARMACIST)
        self.assertTrue(donor.is_demo_account)
        self.assertTrue(pharmacist.is_demo_account)
        self.assertTrue(pharmacist.is_active)


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
