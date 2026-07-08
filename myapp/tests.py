from django.core.management import call_command
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import FileSystemStorage, storages
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
import base64
from datetime import timedelta
from decimal import Decimal
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, call, patch

from .models import Medicine, User
from .services.ai import (
    MISSING_API_KEY_MESSAGE,
    OCR_SPACE_AFTER_GEMINI_MESSAGE,
    OCR_SPACE_EMPTY_TEXT_MESSAGE,
    PERMISSION_FALLBACK_MESSAGE,
    QUOTA_FALLBACK_MESSAGE,
    analyze_medicine_image,
    analyze_with_ocr_space,
)
from .services.analytics import calculate_demo_analytics
from .services.decision import make_ai_decision
from .services.demo_data import (
    DEMO_BATCH_PREFIX,
    DEMO_DONOR_EMAIL,
    DEMO_PATIENT_EMAIL,
    DEMO_PHARMACIST_EMAIL,
)
from .services.dashboard import get_dashboard_charts, get_dashboard_statistics
from .services.explanation import build_explanation
from .services.fallback import get_ocr_fallback_result
from .services.pipeline import evaluate_donation
from .services.qr import ensure_medicine_qr, generate_qr_identifier, lookup_qr, qr_payload, render_qr_data_uri
from .services.reports import (
    generate_affordability_report,
    generate_csr_report,
    generate_overall_report,
    generate_waste_report,
    generate_weekly_report,
)
from .services.reservations import release_expired_reservations, reserve_medicine, verify_pickup_otp
from .services.safety import analyze_image_safety, calculate_donation_risk


STATICFILES_TEST_STORAGE = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}
LOCAL_MEDIA_TEST_STORAGE = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": STATICFILES_TEST_STORAGE,
}
CLOUDINARY_MEDIA_TEST_STORAGE = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": STATICFILES_TEST_STORAGE,
}


def create_test_image(name="package.png", size=(2200, 1400), color=(20, 120, 90)):
    from PIL import Image

    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


def fake_image_file(name="package.jpg", content=b"same image bytes"):
    return SimpleUploadedFile(name, content, content_type="image/jpeg")


class FakeQuotaError(Exception):
    status_code = 429


class FakePermissionError(Exception):
    status_code = 403


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


class RegistrationTests(TestCase):
    def _registration_payload(self, **overrides):
        payload = {
            "full_name": "Amina Rahman",
            "username": "aminauser",
            "nid": "19981234567890123",
            "phone": "01711111111",
            "role": User.Role.DONOR,
            "license_number": "",
            "password1": "SecureAccess2026!",
            "password2": "SecureAccess2026!",
        }
        payload.update(overrides)
        return payload

    def _professional_section_tag(self, response):
        html = response.content.decode()
        start = html.index('id="professional-verification-section"')
        tag_start = html.rfind("<section", 0, start)
        tag_end = html.index(">", start)
        return html[tag_start:tag_end]

    def test_signup_page_only_shows_public_account_types(self):
        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User")
        self.assertContains(response, "Healthcare Verifier")
        self.assertNotContains(response, "Patient")
        self.assertNotContains(response, "Admin")

    def test_user_role_hides_license_field_by_default(self):
        response = self.client.get(reverse("signup"))

        self.assertIn("hidden", self._professional_section_tag(response))

    def test_user_registration_saves_nid_full_name_and_logs_in(self):
        response = self.client.post(reverse("signup"), self._registration_payload())

        self.assertRedirects(response, reverse("marketplace"), fetch_redirect_response=False)
        user = User.objects.get(username="aminauser")
        self.assertEqual(user.role, User.Role.DONOR)
        self.assertEqual(user.first_name, "Amina")
        self.assertEqual(user.last_name, "Rahman")
        self.assertEqual(user.nid, "19981234567890123")
        self.assertEqual(user.phone, "01711111111")
        self.assertEqual(user.license_number, "")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_healthcare_verifier_shows_license_field_and_requires_license(self):
        response = self.client.post(
            reverse("signup"),
            self._registration_payload(
                username="verifiermissinglicense",
                role=User.Role.PHARMACIST,
                license_number="",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("hidden", self._professional_section_tag(response))
        self.assertContains(response, "Pharmacy license number is required for Healthcare Verifiers.")
        self.assertFalse(User.objects.filter(username="verifiermissinglicense").exists())

    def test_healthcare_verifier_registration_saves_license_and_waits_for_approval(self):
        response = self.client.post(
            reverse("signup"),
            self._registration_payload(
                full_name="Dr Farhan Kabir",
                username="farhanverifier",
                role=User.Role.PHARMACIST,
                license_number="PHARM-2026-009",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registration Received!")
        user = User.objects.get(username="farhanverifier")
        self.assertEqual(user.role, User.Role.PHARMACIST)
        self.assertEqual(user.license_number, "PHARM-2026-009")
        self.assertEqual(user.first_name, "Dr")
        self.assertEqual(user.last_name, "Farhan Kabir")
        self.assertEqual(user.nid, "19981234567890123")
        self.assertFalse(user.is_active)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_existing_registration_flow_still_accepts_valid_user_data(self):
        response = self.client.post(
            reverse("signup"),
            self._registration_payload(username="regularflowuser", nid="20001234567890123"),
        )

        self.assertRedirects(response, reverse("marketplace"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="regularflowuser", role=User.Role.DONOR).exists())


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


class SafetyScreeningTests(TestCase):
    def test_low_risk_donation(self):
        ocr_result = {
            "medicine_name": "Napa",
            "batch_number": "A1",
            "expiry_text": "EXP 12/2028",
            "confidence": 0.92,
        }
        safety_result = analyze_image_safety(fake_image_file(content=b"x" * 2048), ocr_result)
        risk = calculate_donation_risk(ocr_result, safety_result)

        self.assertFalse(safety_result["tampered_seal"])
        self.assertFalse(safety_result["unclear_expiry"])
        self.assertEqual(risk["risk_score"], 0)
        self.assertEqual(risk["risk_level"], "Low")
        self.assertEqual(risk["reasons"], [])

    def test_medium_risk_donation(self):
        ocr_result = {
            "medicine_name": "Napa",
            "batch_number": "",
            "expiry_text": "EXP 12/2028",
            "confidence": 0.65,
        }
        safety_result = analyze_image_safety(fake_image_file(content=b"x" * 2048), ocr_result)
        risk = calculate_donation_risk(ocr_result, safety_result)

        self.assertEqual(risk["risk_score"], 40)
        self.assertEqual(risk["risk_level"], "Medium")
        self.assertIn("OCR confidence is below 0.8.", risk["reasons"])
        self.assertIn("Batch number is missing.", risk["reasons"])

    def test_high_risk_donation(self):
        ocr_result = {
            "medicine_name": "Opened seal medicine",
            "batch_number": "",
            "expiry_text": "",
            "confidence": 0.51,
        }
        safety_result = analyze_image_safety(fake_image_file(name="opened-seal.jpg", content=b"x" * 2048), ocr_result)
        risk = calculate_donation_risk(ocr_result, safety_result)

        self.assertTrue(safety_result["tampered_seal"])
        self.assertTrue(safety_result["unclear_expiry"])
        self.assertEqual(risk["risk_score"], 100)
        self.assertEqual(risk["risk_level"], "High")
        self.assertIn("Tampering or seal issue detected.", risk["reasons"])

    def test_risk_score_is_capped_at_100(self):
        ocr_result = {
            "batch_number": "",
            "expiry_text": "",
            "confidence": 0.0,
        }
        safety_result = {"unclear_expiry": True, "tampered_seal": True}
        risk = calculate_donation_risk(ocr_result, safety_result)

        self.assertEqual(risk["risk_score"], 100)
        self.assertEqual(risk["risk_level"], "High")

    def test_missing_ocr_fields_are_handled(self):
        safety_result = analyze_image_safety(fake_image_file(content=b"x" * 2048), {})
        risk = calculate_donation_risk({}, safety_result)

        self.assertTrue(safety_result["unclear_expiry"])
        self.assertEqual(risk["risk_score"], 70)
        self.assertEqual(risk["risk_level"], "High")
        self.assertIn("Expiry is unclear or missing.", risk["reasons"])
        self.assertIn("OCR confidence is below 0.8.", risk["reasons"])
        self.assertIn("Batch number is missing.", risk["reasons"])


class DonationDecisionTests(TestCase):
    def test_accept_decision(self):
        decision = make_ai_decision(
            {"confidence": 0.91},
            {
                "damaged_packaging": False,
                "tampered_seal": False,
                "unclear_expiry": False,
                "suspicious_condition": False,
                "low_image_quality": False,
            },
            {"risk_score": 20},
        )

        self.assertEqual(decision["decision"], "accept")
        self.assertEqual(decision["confidence"], 0.90)
        self.assertEqual(
            decision["reasons"],
            ["Risk is low, no safety issues were detected, and OCR confidence is acceptable."],
        )

    def test_review_because_of_ocr_confidence(self):
        decision = make_ai_decision(
            {"confidence": 0.72},
            {"unclear_expiry": False, "tampered_seal": False, "damaged_packaging": False},
            {"risk_score": 20},
        )

        self.assertEqual(decision["decision"], "review")
        self.assertEqual(decision["confidence"], 0.65)
        self.assertEqual(decision["reasons"], ["OCR confidence is below 0.8."])

    def test_review_because_of_unclear_expiry(self):
        decision = make_ai_decision(
            {"confidence": 0.91},
            {"unclear_expiry": True, "tampered_seal": False, "damaged_packaging": False},
            {"risk_score": 20},
        )

        self.assertEqual(decision["decision"], "review")
        self.assertEqual(decision["confidence"], 0.65)
        self.assertEqual(decision["reasons"], ["Expiry is unclear."])

    def test_reject_because_of_tampering(self):
        decision = make_ai_decision(
            {"confidence": 0.91},
            {"tampered_seal": True, "damaged_packaging": False, "unclear_expiry": False},
            {"risk_score": 20},
        )

        self.assertEqual(decision["decision"], "reject")
        self.assertEqual(decision["confidence"], 0.95)
        self.assertEqual(decision["reasons"], ["Tampered seal was detected."])

    def test_reject_because_of_damage(self):
        decision = make_ai_decision(
            {"confidence": 0.91},
            {"damaged_packaging": True, "tampered_seal": False, "unclear_expiry": False},
            {"risk_score": 20},
        )

        self.assertEqual(decision["decision"], "reject")
        self.assertEqual(decision["confidence"], 0.95)
        self.assertEqual(decision["reasons"], ["Damaged packaging was detected."])

    def test_reject_because_of_high_risk(self):
        decision = make_ai_decision(
            {"confidence": 0.91},
            {"damaged_packaging": False, "tampered_seal": False, "unclear_expiry": False},
            {"risk_score": 70},
        )

        self.assertEqual(decision["decision"], "reject")
        self.assertEqual(decision["confidence"], 0.95)
        self.assertEqual(decision["reasons"], ["Risk score is 70 or higher."])

    def test_multiple_simultaneous_reject_reasons(self):
        decision = make_ai_decision(
            {"confidence": 0.55},
            {"damaged_packaging": True, "tampered_seal": True, "unclear_expiry": True},
            {"risk_score": 88},
        )

        self.assertEqual(decision["decision"], "reject")
        self.assertEqual(decision["confidence"], 0.95)
        self.assertEqual(
            decision["reasons"],
            [
                "Risk score is 70 or higher.",
                "Tampered seal was detected.",
                "Damaged packaging was detected.",
            ],
        )


class DonationEvaluationPipelineTests(TestCase):
    def pipeline_results(self, ocr_result, safety_result, risk_result, decision_result):
        image_file = fake_image_file()

        with patch("myapp.services.pipeline.analyze_medicine_image", return_value=ocr_result) as mock_ocr:
            with patch("myapp.services.pipeline.analyze_image_safety", return_value=safety_result) as mock_safety:
                with patch("myapp.services.pipeline.calculate_donation_risk", return_value=risk_result) as mock_risk:
                    with patch("myapp.services.pipeline.make_ai_decision", return_value=decision_result) as mock_decision:
                        call_order = Mock()
                        call_order.attach_mock(mock_ocr, "ocr")
                        call_order.attach_mock(mock_safety, "safety")
                        call_order.attach_mock(mock_risk, "risk")
                        call_order.attach_mock(mock_decision, "decision")

                        result = evaluate_donation(image_file)

        mock_ocr.assert_called_once_with(image_file)
        mock_safety.assert_called_once_with(image_file, ocr_result)
        mock_risk.assert_called_once_with(ocr_result, safety_result)
        mock_decision.assert_called_once_with(ocr_result, safety_result, risk_result)
        self.assertEqual(
            call_order.mock_calls,
            [
                call.ocr(image_file),
                call.safety(image_file, ocr_result),
                call.risk(ocr_result, safety_result),
                call.decision(ocr_result, safety_result, risk_result),
            ],
        )
        return result

    def test_successful_pipeline_returns_all_sections(self):
        ocr_result = {"source": "gemini", "confidence": 0.91}
        safety_result = {"tampered_seal": False, "unclear_expiry": False}
        risk_result = {"risk_score": 0, "risk_level": "Low", "reasons": []}
        decision_result = {"decision": "accept", "confidence": 0.90, "reasons": ["Accepted."]}

        result = self.pipeline_results(ocr_result, safety_result, risk_result, decision_result)

        self.assertEqual(result["ocr"], ocr_result)
        self.assertEqual(result["safety"], safety_result)
        self.assertEqual(result["risk"], risk_result)
        self.assertEqual(result["decision"], decision_result)

    def test_ocr_space_result_continues_to_risk_and_decision(self):
        ocr_result = {"source": "ocr_space", "confidence": 0.82}
        safety_result = {"tampered_seal": False, "unclear_expiry": False}
        risk_result = {"risk_score": 20, "risk_level": "Low", "reasons": []}
        decision_result = {"decision": "accept", "confidence": 0.90, "reasons": ["Accepted."]}

        result = self.pipeline_results(ocr_result, safety_result, risk_result, decision_result)

        self.assertEqual(result["ocr"]["source"], "ocr_space")
        self.assertEqual(result["risk"], risk_result)
        self.assertEqual(result["decision"], decision_result)

    def test_deterministic_fallback_result_continues_to_risk_and_decision(self):
        ocr_result = {"source": "fallback", "used_fallback": True, "confidence": 0.0}
        safety_result = {"tampered_seal": False, "unclear_expiry": True}
        risk_result = {"risk_score": 70, "risk_level": "High", "reasons": ["Expiry is unclear or missing."]}
        decision_result = {"decision": "reject", "confidence": 0.95, "reasons": ["Risk score is 70 or higher."]}

        result = self.pipeline_results(ocr_result, safety_result, risk_result, decision_result)

        self.assertEqual(result["ocr"]["source"], "fallback")
        self.assertEqual(result["risk"], risk_result)
        self.assertEqual(result["decision"], decision_result)

    def test_high_risk_pipeline_decision_is_reject(self):
        result = self.pipeline_results(
            {"source": "gemini", "confidence": 0.51},
            {"tampered_seal": True, "unclear_expiry": True},
            {"risk_score": 100, "risk_level": "High", "reasons": ["Tampering or seal issue detected."]},
            {"decision": "reject", "confidence": 0.95, "reasons": ["Tampered seal was detected."]},
        )

        self.assertEqual(result["decision"]["decision"], "reject")

    def test_good_pipeline_decision_is_accept(self):
        result = self.pipeline_results(
            {"source": "gemini", "confidence": 0.95},
            {"tampered_seal": False, "unclear_expiry": False},
            {"risk_score": 0, "risk_level": "Low", "reasons": []},
            {
                "decision": "accept",
                "confidence": 0.90,
                "reasons": ["Risk is low, no safety issues were detected, and OCR confidence is acceptable."],
            },
        )

        self.assertEqual(result["decision"]["decision"], "accept")


class DonationExplanationTests(TestCase):
    def evaluation_result(self, decision="accept", risk_score=0, risk_level="Low", **overrides):
        evaluation = {
            "ocr": {
                "medicine_name": "Napa",
                "scientific_name": "Paracetamol",
                "dosage": "500 mg",
                "manufacturer": "Beximco",
                "batch_number": "A1",
                "expiry_text": "EXP 12/2028",
                "confidence": 0.91,
                "source": "gemini",
            },
            "safety": {
                "damaged_packaging": False,
                "tampered_seal": False,
                "unclear_expiry": False,
                "suspicious_condition": False,
                "low_image_quality": False,
            },
            "risk": {
                "risk_score": risk_score,
                "risk_level": risk_level,
                "reasons": [],
            },
            "decision": {
                "decision": decision,
                "confidence": 0.90,
                "reasons": ["Risk is low, no safety issues were detected, and OCR confidence is acceptable."],
            },
        }
        for section, values in overrides.items():
            evaluation[section].update(values)
        return evaluation

    def test_accept_explanation(self):
        explanation = build_explanation(self.evaluation_result())

        self.assertEqual(explanation["title"], "Medicine appears suitable for donation")
        self.assertIn("recommendation is accept", explanation["summary"])

    def test_review_explanation(self):
        explanation = build_explanation(
            self.evaluation_result(
                decision="review",
                risk_score=40,
                risk_level="Medium",
                ocr={"confidence": 0.65},
            )
        )

        self.assertEqual(explanation["title"], "Manual review recommended")
        self.assertIn("OCR confidence is low", explanation["negative_points"])

    def test_reject_explanation(self):
        explanation = build_explanation(
            self.evaluation_result(
                decision="reject",
                risk_score=100,
                risk_level="High",
                safety={"tampered_seal": True},
            )
        )

        self.assertEqual(explanation["title"], "Medicine should not be donated")
        self.assertIn("Tampered seal detected", explanation["negative_points"])

    def test_positive_list(self):
        explanation = build_explanation(self.evaluation_result())

        self.assertIn("Medicine identified successfully", explanation["positive_points"])
        self.assertIn("Packaging appears intact", explanation["positive_points"])
        self.assertIn("Expiry information detected", explanation["positive_points"])
        self.assertIn("OCR confidence is high", explanation["positive_points"])

    def test_negative_list(self):
        explanation = build_explanation(
            self.evaluation_result(
                risk_score=70,
                risk_level="High",
                ocr={"batch_number": "", "expiry_text": "", "confidence": 0.4},
                safety={
                    "damaged_packaging": True,
                    "tampered_seal": True,
                    "unclear_expiry": True,
                    "suspicious_condition": True,
                    "low_image_quality": True,
                },
            )
        )

        self.assertIn("Low image quality detected", explanation["negative_points"])
        self.assertIn("Batch number missing", explanation["negative_points"])
        self.assertIn("Tampered seal detected", explanation["negative_points"])
        self.assertIn("Risk score is high", explanation["negative_points"])

    def test_summary_generation(self):
        explanation = build_explanation(self.evaluation_result())

        self.assertLessEqual(len(explanation["summary"].split()), 80)
        self.assertIn("successfully identified", explanation["summary"])
        self.assertIn("risk score is low", explanation["summary"])


class GeminiOcrFoundationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_default_gemini_model_is_current_flash_model(self):
        self.assertEqual(settings.GEMINI_MODEL, "gemini-2.5-flash")
        self.assertNotEqual(settings.GEMINI_MODEL, "gemini-2.0-flash")
        self.assertIn("gemini-2.5-flash-lite", settings.GEMINI_FALLBACK_MODELS)

    @override_settings(GEMINI_API_KEY="", OCR_SPACE_ENABLED=False, OCR_SPACE_API_KEY="")
    def test_missing_api_key_uses_fallback(self):
        with self.assertLogs("myapp.services.ai", level="WARNING"):
            result = analyze_medicine_image(fake_image_file())

        self.assertEqual(result, get_ocr_fallback_result(MISSING_API_KEY_MESSAGE))
        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["message"], MISSING_API_KEY_MESSAGE)

    @override_settings(
        GEMINI_API_KEY="demo-key",
        GEMINI_MODEL="gemini-test",
        GEMINI_FALLBACK_MODELS=[],
        OCR_SPACE_ENABLED=False,
        OCR_SPACE_API_KEY="",
    )
    @patch("myapp.services.ai._generate_gemini_text", return_value="not valid json")
    def test_invalid_gemini_response_uses_fallback(self, _mock_generate):
        with self.assertLogs("myapp.services.ai", level="ERROR") as logs:
            result = analyze_medicine_image(fake_image_file())

        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["source"], "fallback")
        self.assertIn("Gemini OCR returned invalid JSON.", "\n".join(logs.output))
        self.assertIn("Raw Gemini OCR response", "\n".join(logs.output))

    @override_settings(
        GEMINI_API_KEY="demo-key",
        GEMINI_MODEL="gemini-test",
        GEMINI_FALLBACK_MODELS=[],
        OCR_SPACE_ENABLED=False,
        OCR_SPACE_API_KEY="",
    )
    @patch("myapp.services.ai._generate_gemini_text", side_effect=FakeQuotaError("429 quota exceeded"))
    def test_simulated_gemini_429_error_uses_quota_message(self, _mock_generate):
        with self.assertLogs("myapp.services.ai", level="INFO"):
            result = analyze_medicine_image(fake_image_file())

        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["message"], QUOTA_FALLBACK_MESSAGE)

    @override_settings(
        GEMINI_API_KEY="demo-key",
        GEMINI_MODEL="gemini-test",
        GEMINI_FALLBACK_MODELS=[],
        OCR_SPACE_ENABLED=False,
        OCR_SPACE_API_KEY="",
    )
    @patch("myapp.services.ai._generate_gemini_text", side_effect=FakePermissionError("403 PERMISSION_DENIED"))
    def test_simulated_gemini_403_error_uses_permission_message(self, _mock_generate):
        with self.assertLogs("myapp.services.ai", level="INFO"):
            result = analyze_medicine_image(fake_image_file())

        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["message"], PERMISSION_FALLBACK_MESSAGE)

    @override_settings(
        GEMINI_API_KEY="demo-key",
        GEMINI_MODEL="gemini-test",
        GEMINI_FALLBACK_MODELS=[],
        OCR_SPACE_ENABLED=True,
        OCR_SPACE_API_KEY="ocr-key",
    )
    @patch("myapp.services.ai._generate_gemini_text", side_effect=FakeQuotaError("429 quota exceeded"))
    @patch(
        "myapp.services.ai._post_ocr_space",
        return_value='{"IsErroredOnProcessing":false,"ParsedResults":[{"ParsedText":"Napa Extra\\n500 mg\\nBatch A1\\nEXP 12/2028\\nBeximco Pharmaceuticals Ltd"}]}',
    )
    def test_gemini_unavailable_uses_ocr_space_success(self, mock_ocr_space, mock_gemini):
        with self.assertLogs("myapp.services.ai", level="INFO"):
            result = analyze_medicine_image(fake_image_file())

        self.assertEqual(result["source"], "ocr_space")
        self.assertFalse(result["used_fallback"])
        self.assertEqual(result["medicine_name"], "Napa Extra")
        self.assertEqual(result["dosage"], "500 mg")
        self.assertEqual(result["batch_number"], "A1")
        self.assertEqual(result["message"], OCR_SPACE_AFTER_GEMINI_MESSAGE)
        self.assertEqual(mock_gemini.call_count, 1)
        self.assertEqual(mock_ocr_space.call_count, 1)

    @override_settings(
        GEMINI_API_KEY="demo-key",
        GEMINI_MODEL="gemini-first",
        GEMINI_FALLBACK_MODELS=["gemini-second"],
        OCR_SPACE_ENABLED=False,
        OCR_SPACE_API_KEY="",
    )
    @patch(
        "myapp.services.ai._generate_gemini_text",
        side_effect=[
            FakeQuotaError("429 quota exceeded"),
            '{"medicine_name":"Napa","scientific_name":"Paracetamol","dosage":"500 mg","manufacturer":"Beximco","batch_number":"A1","expiry_text":"EXP 12/2028","confidence":0.82}',
        ],
    )
    def test_first_gemini_quota_failure_tries_next_model(self, mock_gemini):
        with self.assertLogs("myapp.services.ai", level="INFO"):
            result = analyze_medicine_image(fake_image_file())

        self.assertEqual(result["source"], "gemini")
        self.assertEqual(result["medicine_name"], "Napa")
        self.assertEqual(mock_gemini.call_args_list[0].args[1], "gemini-first")
        self.assertEqual(mock_gemini.call_args_list[1].args[1], "gemini-second")

    @override_settings(GEMINI_API_KEY="", OCR_SPACE_ENABLED=True, OCR_SPACE_API_KEY="ocr-key")
    @patch(
        "myapp.services.ai._post_ocr_space",
        return_value='{"IsErroredOnProcessing":false,"ParsedResults":[{"ParsedText":""}]}',
    )
    def test_ocr_space_empty_parsed_text_returns_clear_fallback_message(self, _mock_ocr_space):
        with self.assertLogs("myapp.services.ai", level="INFO"):
            result = analyze_medicine_image(fake_image_file())

        self.assertEqual(result["source"], "fallback")
        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["message"], OCR_SPACE_EMPTY_TEXT_MESSAGE)

    @override_settings(OCR_SPACE_ENABLED=True, OCR_SPACE_API_KEY="ocr-key")
    @patch(
        "myapp.services.ai._post_ocr_space",
        return_value='{"IsErroredOnProcessing":false,"ParsedResults":[{"ParsedText":"Losectil 20mg Capsule\\nLOT ZX-44\\nExpiry 05/2028\\nSquare Pharma Limited"}]}',
    )
    def test_ocr_space_result_parsing(self, _mock_ocr_space):
        result = analyze_with_ocr_space(fake_image_file())

        self.assertEqual(result["source"], "ocr_space")
        self.assertEqual(result["medicine_name"], "Losectil 20mg Capsule")
        self.assertEqual(result["dosage"], "20mg")
        self.assertEqual(result["batch_number"], "ZX-44")
        self.assertEqual(result["expiry_text"], "Expiry 05/2028")
        self.assertEqual(result["manufacturer"], "Square Pharma Limited")
        self.assertEqual(result["confidence"], 0.6)

    @override_settings(GEMINI_API_KEY="demo-key", GEMINI_MODEL="gemini-test", GEMINI_FALLBACK_MODELS=[])
    @patch(
        "myapp.services.ai._generate_gemini_text",
        return_value='```json\n{"medicine_name":"Napa","scientific_name":"Paracetamol","dosage":"500 mg","manufacturer":"Beximco","batch_number":"A1","expiry_text":"EXP 12/2028","confidence":0.87}\n```',
    )
    def test_markdown_fenced_gemini_json_is_parsed(self, _mock_generate):
        result = analyze_medicine_image(fake_image_file())

        self.assertEqual(result["source"], "gemini")
        self.assertFalse(result["used_fallback"])
        self.assertEqual(result["medicine_name"], "Napa")
        self.assertEqual(result["confidence"], 0.87)

    @override_settings(GEMINI_API_KEY="demo-key", GEMINI_MODEL="gemini-test", GEMINI_FALLBACK_MODELS=[])
    @patch(
        "myapp.services.ai._generate_gemini_text",
        return_value='{"medicine_name":"Napa","scientific_name":"Paracetamol","dosage":"500 mg","manufacturer":"Beximco","batch_number":"A1","expiry_text":"EXP 12/2028","confidence":0.87}',
    )
    def test_cache_hit_avoids_repeated_ai_calls(self, mock_generate):
        first = analyze_medicine_image(fake_image_file())
        second = analyze_medicine_image(fake_image_file())

        self.assertEqual(first, second)
        self.assertEqual(first["source"], "gemini")
        self.assertEqual(mock_generate.call_count, 1)

    @override_settings(DEMO_MODE=False)
    def test_ocr_page_returns_404_when_demo_mode_false(self):
        response = self.client.get(reverse("judge_ocr"))

        self.assertEqual(response.status_code, 404)

class JudgeOcrPipelinePageTests(TestCase):
    def evaluation_result(self, source="gemini", decision="accept", risk_score=0, risk_level="Low"):
        return {
            "ocr": {
                "medicine_name": "Napa",
                "scientific_name": "Paracetamol",
                "dosage": "500 mg",
                "manufacturer": "Beximco",
                "batch_number": "A1",
                "expiry_text": "EXP 12/2028",
                "confidence": 0.91,
                "source": source,
            },
            "safety": {
                "damaged_packaging": False,
                "tampered_seal": decision == "reject",
                "unclear_expiry": decision == "reject",
                "suspicious_condition": False,
                "low_image_quality": False,
            },
            "risk": {
                "risk_score": risk_score,
                "risk_level": risk_level,
                "reasons": [] if risk_score == 0 else ["Risk score is 70 or higher."],
            },
            "decision": {
                "decision": decision,
                "confidence": 0.90 if decision == "accept" else 0.95,
                "reasons": [
                    "Risk is low, no safety issues were detected, and OCR confidence is acceptable."
                    if decision == "accept"
                    else "Tampered seal was detected."
                ],
            },
        }

    @override_settings(DEMO_MODE=True)
    def test_get_page_loads_upload_form_only(self):
        response = self.client.get(reverse("judge_ocr"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Medicine OCR Test")
        self.assertContains(response, "Medicine package image")
        self.assertNotContains(response, "Risk Assessment")
        self.assertIsNone(response.context["evaluation"])

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_post_valid_image_calls_pipeline_once(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()

        response = self.client.post(reverse("judge_ocr"), {"medicine_image": fake_image_file()})

        self.assertEqual(response.status_code, 200)
        mock_evaluate.assert_called_once()
        self.assertEqual(mock_evaluate.call_args.args[0].name, "package.jpg")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_template_receives_evaluation(self, mock_evaluate):
        evaluation = self.evaluation_result()
        mock_evaluate.return_value = evaluation

        response = self.client.post(reverse("judge_ocr"), {"medicine_image": fake_image_file()})

        self.assertEqual(response.context["evaluation"], evaluation)
        self.assertEqual(response.context["explanation"]["title"], "Medicine appears suitable for donation")
        self.assertContains(response, "OCR")
        self.assertContains(response, "Safety Screening")
        self.assertContains(response, "Risk Assessment")
        self.assertContains(response, "AI Decision")
        self.assertContains(response, "Explanation")
        self.assertContains(response, "Medicine appears suitable for donation")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_fallback_result_renders_correctly(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result(
            source="fallback",
            decision="reject",
            risk_score=70,
            risk_level="High",
        )

        response = self.client.post(reverse("judge_ocr"), {"medicine_image": fake_image_file()})

        self.assertContains(response, "fallback")
        self.assertContains(response, "Risk score is 70 or higher.")
        self.assertContains(response, "Reject")
        self.assertContains(response, "Medicine should not be donated")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_high_risk_reject_renders_correctly(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result(
            source="gemini",
            decision="reject",
            risk_score=100,
            risk_level="High",
        )

        response = self.client.post(reverse("judge_ocr"), {"medicine_image": fake_image_file()})

        self.assertContains(response, "High")
        self.assertContains(response, "Reject")
        self.assertContains(response, "text-red-700")
        self.assertContains(response, "✓ Yes")
        self.assertContains(response, "Tampered seal detected")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_accept_renders_correctly(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()

        response = self.client.post(reverse("judge_ocr"), {"medicine_image": fake_image_file()})

        self.assertContains(response, "Low")
        self.assertContains(response, "Accept")
        self.assertContains(response, "text-emerald-700")
        self.assertContains(response, "✗ No")
        self.assertContains(response, "Packaging appears intact")


class PharmacistReviewWorkflowTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.donor = User.objects.create_user(
            username="review_donor",
            email="review-donor@example.com",
            password="pass12345",
            role=User.Role.DONOR,
        )
        self.pharmacist = User.objects.create_user(
            username="review_pharmacist",
            password="pass12345",
            role=User.Role.PHARMACIST,
            is_active=True,
        )
        self.medicine = Medicine.objects.create(
            donor=self.donor,
            name="Review Medicine",
            scientific_name="Review Scientific",
            batch_number="REVIEW-001",
            expiry_date="2028-05-20",
            original_price=Decimal("500.00"),
            status="pending",
            medicine_image=create_test_image("review-package.png", size=(900, 900)),
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def evaluation_result(self, decision="accept", risk_score=0, risk_level="Low"):
        return {
            "ocr": {
                "medicine_name": "AI Review Medicine",
                "scientific_name": "AI Scientific",
                "dosage": "500 mg",
                "manufacturer": "Beximco",
                "batch_number": "AI-BATCH-1",
                "expiry_text": "EXP 12/2028",
                "confidence": 0.91 if decision == "accept" else 0.55,
                "source": "gemini",
            },
            "safety": {
                "damaged_packaging": False,
                "tampered_seal": decision == "reject",
                "unclear_expiry": decision == "reject",
                "suspicious_condition": False,
                "low_image_quality": False,
            },
            "risk": {
                "risk_score": risk_score,
                "risk_level": risk_level,
                "reasons": [] if risk_score == 0 else ["Risk score is 70 or higher."],
            },
            "decision": {
                "decision": decision,
                "confidence": 0.90 if decision == "accept" else 0.95,
                "reasons": [
                    "Risk is low, no safety issues were detected, and OCR confidence is acceptable."
                    if decision == "accept"
                    else "Tampered seal was detected."
                ],
            },
        }

    def review_url(self):
        return reverse("pharmacist_review", args=[self.medicine.id])

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_pharmacist_review_page_loads(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)

        response = self.client.get(self.review_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pharmacist Review")
        self.assertContains(response, "Medicine Image")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_existing_ai_evaluation_renders(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)

        response = self.client.get(self.review_url())

        self.assertContains(response, "AI Review Medicine")
        self.assertContains(response, "AI Recommendation")
        self.assertContains(response, "Risk Score")
        self.assertContains(response, "Explanation Summary")
        self.assertContains(response, "Positive Findings")
        self.assertContains(response, "Negative Findings")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_approve_updates_verification_status(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)

        response = self.client.post(self.review_url(), {"action": "approve"})

        self.assertContains(response, "Medicine verified successfully.")
        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.status, "verified")
        self.assertIsNotNone(self.medicine.verified_at)
        self.assertEqual(self.medicine.rejection_reason, "")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_reject_updates_verification_status(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result(decision="reject", risk_score=100, risk_level="High")
        self.client.force_login(self.pharmacist)

        response = self.client.post(self.review_url(), {
            "action": "reject",
            "rejection_reason": "Seal appears opened.",
        })

        self.assertContains(response, "Medicine rejected successfully.")
        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.status, "rejected")
        self.assertIsNotNone(self.medicine.rejected_at)

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_reject_stores_reason(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result(decision="reject", risk_score=100, risk_level="High")
        self.client.force_login(self.pharmacist)

        self.client.post(self.review_url(), {
            "action": "reject",
            "rejection_reason": "Seal appears opened.",
        })

        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.rejection_reason, "Seal appears opened.")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_reject_requires_reason(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result(decision="reject", risk_score=100, risk_level="High")
        self.client.force_login(self.pharmacist)

        response = self.client.post(self.review_url(), {"action": "reject", "rejection_reason": ""})

        self.assertContains(response, "Reason for rejection is required.")
        self.assertNotContains(response, "Medicine rejected successfully.")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_ai_recommendation_is_displayed(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result(decision="reject", risk_score=100, risk_level="High")
        self.client.force_login(self.pharmacist)

        response = self.client.get(self.review_url())

        self.assertContains(response, "AI Recommendation")
        self.assertContains(response, "Reject")
        self.assertContains(response, "AI Confidence")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_human_decision_panel_is_displayed(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)

        response = self.client.get(self.review_url())

        self.assertContains(response, "Human Decision")
        self.assertContains(response, "Approve")
        self.assertContains(response, "Reject")
        self.assertContains(response, "Reason for rejection")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_ai_assists_pharmacist_decides_message_is_rendered(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)

        response = self.client.get(self.review_url())

        self.assertContains(response, "AI assists. Pharmacist decides.")
        self.assertContains(response, "AI provides recommendations. The pharmacist makes the final decision.")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_verified_medicine_appears_on_donor_dashboard(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)
        self.client.post(self.review_url(), {"action": "approve"})

        self.client.force_login(self.donor)
        response = self.client.get(reverse("profile"))

        self.assertContains(response, "Review Medicine")
        self.assertContains(response, "Verified")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_rejected_medicine_appears_on_donor_dashboard(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result(decision="reject", risk_score=100, risk_level="High")
        self.client.force_login(self.pharmacist)
        self.client.post(self.review_url(), {
            "action": "reject",
            "rejection_reason": "Expiry text unreadable.",
        })

        self.client.force_login(self.donor)
        response = self.client.get(reverse("profile"))

        self.assertContains(response, "Review Medicine")
        self.assertContains(response, "Rejected")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_dashboard_shows_rejection_reason(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result(decision="reject", risk_score=100, risk_level="High")
        self.client.force_login(self.pharmacist)
        self.client.post(self.review_url(), {
            "action": "reject",
            "rejection_reason": "Expiry text unreadable.",
        })

        self.client.force_login(self.donor)
        response = self.client.get(reverse("profile"))

        self.assertContains(response, "Rejection Reason:")
        self.assertContains(response, "Expiry text unreadable.")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_reviewed_medicines_cannot_be_reviewed_again(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)
        self.client.post(self.review_url(), {"action": "approve"})

        response = self.client.get(self.review_url())

        self.assertContains(response, "Verified by Pharmacist")
        self.assertContains(response, "Further review actions are disabled.")
        self.assertNotContains(response, 'name="action" value="approve"')

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_no_duplicate_reviews(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)
        self.client.post(self.review_url(), {"action": "approve"})
        self.client.post(self.review_url(), {
            "action": "reject",
            "rejection_reason": "Trying to overwrite.",
        })

        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.status, "verified")
        self.assertEqual(self.medicine.rejection_reason, "")

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_qr_id_generated_after_approval(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)

        response = self.client.post(self.review_url(), {"action": "approve"})

        self.medicine.refresh_from_db()
        self.assertRegex(self.medicine.qr_code_id, r"^RMD-[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}$")
        self.assertIsNotNone(self.medicine.qr_generated_at)
        self.assertContains(response, "QR Generated Successfully")
        self.assertContains(response, self.medicine.qr_code_id)

    def test_qr_ids_are_unique(self):
        qr_ids = {generate_qr_identifier() for _ in range(100)}

        self.assertEqual(len(qr_ids), 100)

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_qr_contains_only_qr_id(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)
        self.client.post(self.review_url(), {"action": "approve"})
        self.medicine.refresh_from_db()

        payload = qr_payload(self.medicine.qr_code_id)

        self.assertEqual(payload, self.medicine.qr_code_id)
        self.assertNotIn(str(self.donor.id), payload)
        self.assertNotIn(self.donor.username, payload)
        self.assertNotIn(self.donor.email, payload)

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_qr_lookup_returns_correct_medicine(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)
        self.client.post(self.review_url(), {"action": "approve"})
        self.medicine.refresh_from_db()

        result = lookup_qr(self.medicine.qr_code_id)

        self.assertEqual(result["medicine"], self.medicine)
        self.assertEqual(result["donation"], self.medicine)

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_qr_lookup_returns_correct_donor(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)
        self.client.post(self.review_url(), {"action": "approve"})
        self.medicine.refresh_from_db()

        result = lookup_qr(self.medicine.qr_code_id)

        self.assertEqual(result["donor"], self.donor)

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_public_qr_contains_no_donor_information(self, mock_evaluate):
        self.donor.email = "private-donor@example.com"
        self.donor.save()
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)
        self.client.post(self.review_url(), {"action": "approve"})
        self.medicine.refresh_from_db()

        payload = qr_payload(self.medicine.qr_code_id)

        self.assertNotIn("review_donor", payload)
        self.assertNotIn("private-donor@example.com", payload)
        self.assertNotIn("Review Medicine", payload)
        self.assertNotIn("REVIEW-001", payload)

    @override_settings(DEMO_MODE=True)
    @patch("myapp.views.evaluate_donation")
    def test_printable_qr_is_generated(self, mock_evaluate):
        mock_evaluate.return_value = self.evaluation_result()
        self.client.force_login(self.pharmacist)
        response = self.client.post(self.review_url(), {"action": "approve"})
        self.medicine.refresh_from_db()

        qr_image = render_qr_data_uri(self.medicine.qr_code_id)
        png_bytes = base64.b64decode(qr_image.split(",", 1)[1])

        self.assertTrue(qr_image.startswith("data:image/png;base64,"))
        self.assertTrue(png_bytes.startswith(b"\x89PNG"))
        self.assertContains(response, "Download QR")
        self.assertContains(response, f'download="remedi-{self.medicine.qr_code_id}.png"')


class MarketplaceListingTests(TestCase):
    def setUp(self):
        self.donor = User.objects.create_user(
            username="market_donor",
            email="market-donor@example.com",
            password="pass12345",
            role=User.Role.DONOR,
            phone="01700000000",
        )

    def create_medicine(self, name="Napa 500 mg", scientific_name="Paracetamol", status="verified", qr=True, verified_at=None):
        medicine = Medicine.objects.create(
            donor=self.donor,
            name=name,
            scientific_name=scientific_name,
            category="500 mg",
            batch_number=f"BATCH-{name[:4]}",
            expiry_date="2028-05-20",
            original_price=Decimal("100.00"),
            status=status,
            verified_at=verified_at if status == "verified" else None,
            rejected_at=timezone.now() if status == "rejected" else None,
        )
        if qr:
            ensure_medicine_qr(medicine)
        return medicine

    def test_only_approved_medicines_appear(self):
        approved = self.create_medicine(name="Approved Med")
        self.create_medicine(name="Rejected Med", status="rejected")
        self.create_medicine(name="Pending Med", status="pending")

        response = self.client.get(reverse("marketplace_page"))

        self.assertContains(response, approved.name)
        self.assertNotContains(response, "Rejected Med")
        self.assertNotContains(response, "Pending Med")

    def test_rejected_medicines_hidden(self):
        self.create_medicine(name="Rejected Only", status="rejected")

        response = self.client.get(reverse("marketplace_page"))

        self.assertNotContains(response, "Rejected Only")
        self.assertContains(response, "No verified medicines available.")

    def test_pending_medicines_hidden(self):
        self.create_medicine(name="Pending Only", status="pending")

        response = self.client.get(reverse("marketplace_page"))

        self.assertNotContains(response, "Pending Only")
        self.assertContains(response, "No verified medicines available.")

    def test_search_by_medicine_name(self):
        self.create_medicine(name="Napa 500 mg")
        self.create_medicine(name="Seclo 20 mg", scientific_name="Omeprazole")

        response = self.client.get(reverse("marketplace_page"), {"q": "napa"})

        self.assertContains(response, "Napa 500 mg")
        self.assertNotContains(response, "Seclo 20 mg")

    def test_search_by_scientific_name(self):
        self.create_medicine(name="Napa 500 mg", scientific_name="Paracetamol")
        self.create_medicine(name="Seclo 20 mg", scientific_name="Omeprazole")

        response = self.client.get(reverse("marketplace_page"), {"q": "omeprazole"})

        self.assertContains(response, "Seclo 20 mg")
        self.assertNotContains(response, "Napa 500 mg")

    def test_marketplace_detail_page(self):
        medicine = self.create_medicine(name="Detail Med", scientific_name="Detail Scientific")

        response = self.client.get(reverse("marketplace_detail", args=[medicine.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Med")
        self.assertContains(response, "Detail Scientific")
        self.assertContains(response, "Batch Number")
        self.assertContains(response, "Pharmacist Status")
        self.assertContains(response, "QR Verified")

    def test_no_donor_information_exposed(self):
        self.donor.first_name = "Private"
        self.donor.last_name = "Donor"
        self.donor.save()
        medicine = self.create_medicine(name="Privacy Med")

        list_response = self.client.get(reverse("marketplace_page"))
        detail_response = self.client.get(reverse("marketplace_detail", args=[medicine.id]))

        for response in (list_response, detail_response):
            self.assertNotContains(response, self.donor.username)
            self.assertNotContains(response, self.donor.email)
            self.assertNotContains(response, self.donor.phone)
            self.assertNotContains(response, "Private")

    def test_qr_badge_shown_only_when_qr_exists(self):
        self.create_medicine(name="QR Medicine")
        self.create_medicine(name="No QR Medicine", qr=False)

        response = self.client.get(reverse("marketplace_page"))

        self.assertContains(response, "QR Medicine")
        self.assertContains(response, "QR Verified")
        self.assertNotContains(response, "No QR Medicine")

    def test_correct_ordering(self):
        older = self.create_medicine(
            name="Older Approved",
            verified_at=timezone.now() - timedelta(days=2),
        )
        newer = self.create_medicine(
            name="Newer Approved",
            verified_at=timezone.now(),
        )

        response = self.client.get(reverse("marketplace_page"))
        content = response.content.decode()

        self.assertLess(content.index(newer.name), content.index(older.name))

    def test_empty_marketplace(self):
        response = self.client.get(reverse("marketplace_page"))

        self.assertContains(response, "No verified medicines available.")


class ReservationSystemTests(TestCase):
    def setUp(self):
        self.donor = User.objects.create_user(
            username="reservation_donor",
            email="reservation-donor@example.com",
            password="pass12345",
            role=User.Role.DONOR,
        )
        self.patient = User.objects.create_user(
            username="reservation_patient",
            password="pass12345",
            role=User.Role.PATIENT,
        )
        self.other_patient = User.objects.create_user(
            username="other_patient",
            password="pass12345",
            role=User.Role.PATIENT,
        )
        self.pharmacist = User.objects.create_user(
            username="pickup_pharmacist",
            password="pass12345",
            role=User.Role.PHARMACIST,
            is_active=True,
        )
        self.medicine = Medicine.objects.create(
            donor=self.donor,
            name="Reservation Med",
            scientific_name="Reservation Scientific",
            category="500 mg",
            batch_number="RSV-001",
            expiry_date="2028-05-20",
            original_price=Decimal("100.00"),
            status="verified",
            verified_at=timezone.now(),
        )
        ensure_medicine_qr(self.medicine)

    def reserve(self):
        result = reserve_medicine(self.medicine.id, self.patient)
        self.medicine.refresh_from_db()
        return result

    def test_successful_reservation(self):
        self.client.force_login(self.patient)

        response = self.client.post(reverse("reserve_medicine", args=[self.medicine.id]))

        self.assertContains(response, "Reservation Successful")
        self.assertContains(response, "Reservation Med")
        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.patient, self.patient)
        self.assertIsNotNone(self.medicine.reserved_until)

    def test_otp_generated(self):
        result = self.reserve()

        self.assertTrue(result["otp"])
        self.assertEqual(self.medicine.pickup_otp, result["otp"])
        self.assertIsNotNone(self.medicine.otp_generated_at)

    def test_otp_length_is_6_digits(self):
        self.reserve()

        self.assertEqual(len(self.medicine.pickup_otp), 6)
        self.assertTrue(self.medicine.pickup_otp.isdigit())

    def test_reservation_expiry(self):
        before = timezone.now()
        self.reserve()

        self.assertGreaterEqual(self.medicine.reserved_until, before + timedelta(hours=24))

    def test_expired_reservation_release(self):
        self.reserve()
        Medicine.objects.filter(id=self.medicine.id).update(reserved_until=timezone.now() - timedelta(minutes=1))

        released_count = release_expired_reservations()
        self.medicine.refresh_from_db()

        self.assertEqual(released_count, 1)
        self.assertIsNone(self.medicine.patient)
        self.assertIsNone(self.medicine.reserved_until)
        self.assertEqual(self.medicine.pickup_otp, "")

    def test_wrong_otp(self):
        self.reserve()

        result = verify_pickup_otp(self.medicine.qr_code_id, "000000")
        self.medicine.refresh_from_db()

        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "Invalid OTP")
        self.assertEqual(self.medicine.status, "verified")
        self.assertIsNone(self.medicine.completed_at)

    def test_correct_otp(self):
        self.reserve()

        result = verify_pickup_otp(self.medicine.qr_code_id, self.medicine.pickup_otp)

        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "Medicine collected successfully.")

    def test_already_reserved_medicine(self):
        self.reserve()

        result = reserve_medicine(self.medicine.id, self.other_patient)

        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "This medicine is currently reserved.")

    def test_double_reservation_prevented(self):
        self.reserve()
        reserve_medicine(self.medicine.id, self.other_patient)
        self.medicine.refresh_from_db()

        self.assertEqual(self.medicine.patient, self.patient)

    def test_medicine_marked_collected(self):
        self.reserve()

        verify_pickup_otp(self.medicine.qr_code_id, self.medicine.pickup_otp)
        self.medicine.refresh_from_db()

        self.assertEqual(self.medicine.status, "sold")
        self.assertIsNotNone(self.medicine.completed_at)

    def test_inventory_updated(self):
        self.reserve()

        verify_pickup_otp(self.medicine.qr_code_id, self.medicine.pickup_otp)

        response = self.client.get(reverse("marketplace_page"))
        self.assertNotContains(response, "Reservation Med")

    def test_reservation_removed_after_pickup(self):
        self.reserve()

        verify_pickup_otp(self.medicine.qr_code_id, self.medicine.pickup_otp)
        self.medicine.refresh_from_db()

        self.assertIsNone(self.medicine.reserved_until)
        self.assertEqual(self.medicine.pickup_otp, "")
        self.assertIsNone(self.medicine.otp_generated_at)

    def test_collected_medicine_unavailable_for_future_reservation(self):
        self.reserve()
        verify_pickup_otp(self.medicine.qr_code_id, self.medicine.pickup_otp)

        result = reserve_medicine(self.medicine.id, self.other_patient)

        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "This medicine is not available.")

    def test_pharmacist_pickup_page_verifies_correct_otp(self):
        self.reserve()
        self.client.force_login(self.pharmacist)

        response = self.client.post(reverse("pharmacist_pickup"), {
            "identifier": self.medicine.qr_code_id,
            "otp": self.medicine.pickup_otp,
        })

        self.assertContains(response, "Medicine collected successfully.")

    def test_pharmacist_pickup_page_rejects_wrong_otp(self):
        self.reserve()
        self.client.force_login(self.pharmacist)

        response = self.client.post(reverse("pharmacist_pickup"), {
            "identifier": self.medicine.qr_code_id,
            "otp": "000000",
        })

        self.assertContains(response, "Invalid OTP")


class ImpactDashboardTests(TestCase):
    def setUp(self):
        self.donor = User.objects.create_user(
            username="impact_donor",
            password="pass12345",
            role=User.Role.DONOR,
        )
        self.patient = User.objects.create_user(
            username="impact_patient",
            password="pass12345",
            role=User.Role.PATIENT,
        )

    def create_medicine(
        self,
        name,
        status="pending",
        patient=None,
        completed_at=None,
        reserved_until=None,
        qr=False,
        verified_at="auto",
        is_physical_intact=False,
        is_authentic=False,
        is_expiry_valid=False,
    ):
        if verified_at == "auto":
            verified_at = timezone.now() if status in {"verified", "sold"} else None
        medicine = Medicine.objects.create(
            donor=self.donor,
            name=name,
            scientific_name=f"{name} Scientific",
            batch_number=f"IMPACT-{name[:8]}",
            expiry_date="2028-05-20",
            original_price=Decimal("100.00"),
            status=status,
            patient=patient,
            completed_at=completed_at,
            reserved_until=reserved_until,
            verified_at=verified_at,
            is_physical_intact=is_physical_intact,
            is_authentic=is_authentic,
            is_expiry_valid=is_expiry_valid,
        )
        if qr:
            ensure_medicine_qr(medicine)
        return medicine

    def seed_dashboard_medicines(self):
        self.create_medicine("Pending Med")
        self.create_medicine("Rejected Med", status="rejected")
        self.create_medicine("Listing Med", status="verified", qr=True)
        self.create_medicine(
            "Reserved Med",
            status="verified",
            patient=self.patient,
            reserved_until=timezone.now() + timedelta(hours=2),
            qr=True,
        )
        self.create_medicine(
            "Collected Med",
            status="sold",
            patient=self.patient,
            completed_at=timezone.now(),
            qr=True,
        )

    def test_dashboard_statistics_computed_correctly(self):
        self.seed_dashboard_medicines()

        statistics = get_dashboard_statistics()

        self.assertEqual(statistics["medicines_donated"], 5)
        self.assertEqual(statistics["medicines_approved"], 3)
        self.assertEqual(statistics["medicines_rejected"], 1)
        self.assertEqual(statistics["medicines_reserved"], 1)
        self.assertEqual(statistics["medicines_collected"], 1)
        self.assertEqual(statistics["active_marketplace_listings"], 1)
        self.assertEqual(statistics["estimated_waste_prevented"], 3)
        self.assertEqual(statistics["estimated_patients_helped"], 1)

    def test_approved_count(self):
        self.create_medicine("Approved Med", status="verified")
        self.create_medicine("Collected Med", status="sold", completed_at=timezone.now())
        self.create_medicine("Rejected Med", status="rejected")

        statistics = get_dashboard_statistics()

        self.assertEqual(statistics["medicines_approved"], 2)

    def test_rejected_count(self):
        self.create_medicine("Rejected Med", status="rejected")
        self.create_medicine("Pending Med")

        statistics = get_dashboard_statistics()

        self.assertEqual(statistics["medicines_rejected"], 1)

    def test_marketplace_listing_count(self):
        self.create_medicine("Listing Med", status="verified", qr=True)
        self.create_medicine("No QR Med", status="verified")
        self.create_medicine("Reserved Med", status="verified", patient=self.patient, reserved_until=timezone.now() + timedelta(hours=1), qr=True)

        statistics = get_dashboard_statistics()

        self.assertEqual(statistics["active_marketplace_listings"], 1)

    def test_collected_count(self):
        self.create_medicine("Collected Med", status="sold", completed_at=timezone.now())
        self.create_medicine("Reserved Med", status="verified", patient=self.patient, reserved_until=timezone.now() + timedelta(hours=1))

        statistics = get_dashboard_statistics()

        self.assertEqual(statistics["medicines_collected"], 1)

    def test_reserved_count(self):
        self.create_medicine("Reserved Med", status="verified", patient=self.patient, reserved_until=timezone.now() + timedelta(hours=1))
        self.create_medicine("Expired Med", status="verified", patient=self.patient, reserved_until=timezone.now() - timedelta(hours=1))

        statistics = get_dashboard_statistics()

        self.assertEqual(statistics["medicines_reserved"], 1)

    def test_empty_dashboard(self):
        statistics = get_dashboard_statistics()

        self.assertFalse(statistics["has_data"])
        self.assertEqual(statistics["medicines_donated"], 0)

    def chart_by_title(self, charts, title):
        return next(chart for chart in charts["charts"] if chart["title"] == title)

    def test_dashboard_chart_data_generated_from_medicines(self):
        self.seed_dashboard_medicines()

        charts = get_dashboard_charts()

        self.assertTrue(charts["has_data"])
        self.assertEqual(len(charts["charts"]), 5)

    def test_verification_chart_counts(self):
        self.create_medicine("Approved Med", status="verified")
        self.create_medicine("Collected Med", status="sold", completed_at=timezone.now())
        self.create_medicine("Rejected Med", status="rejected")
        self.create_medicine("Pending Med")

        chart = self.chart_by_title(get_dashboard_charts(), "Verification Outcomes")

        self.assertEqual(chart["labels"], ["Approved", "Rejected", "Pending"])
        self.assertEqual(chart["data"], [2, 1, 1])

    def test_marketplace_chart_counts(self):
        self.create_medicine("Available Med", status="verified", qr=True)
        self.create_medicine("Reserved Med", status="verified", patient=self.patient, reserved_until=timezone.now() + timedelta(hours=1), qr=True)
        self.create_medicine("Collected Med", status="sold", patient=self.patient, completed_at=timezone.now(), qr=True)
        self.create_medicine("No QR Med", status="verified")

        chart = self.chart_by_title(get_dashboard_charts(), "Marketplace Distribution")

        self.assertEqual(chart["labels"], ["Available", "Reserved", "Collected"])
        self.assertEqual(chart["data"], [1, 1, 1])

    def test_risk_chart_counts(self):
        self.create_medicine(
            "Low Risk",
            is_physical_intact=True,
            is_authentic=True,
            is_expiry_valid=True,
        )
        self.create_medicine(
            "Medium Risk",
            is_physical_intact=True,
            is_authentic=True,
            is_expiry_valid=False,
        )
        self.create_medicine(
            "High Risk",
            is_physical_intact=False,
            is_authentic=False,
            is_expiry_valid=True,
        )

        chart = self.chart_by_title(get_dashboard_charts(), "Risk Level Distribution")

        self.assertEqual(chart["labels"], ["Low", "Medium", "High"])
        self.assertEqual(chart["data"], [1, 1, 1])

    def test_medicine_name_aggregation_chart_uses_top_names(self):
        self.create_medicine("Napa")
        self.create_medicine("Napa")
        self.create_medicine("Ace")

        chart = self.chart_by_title(get_dashboard_charts(), "Medicine Categories")

        self.assertEqual(chart["labels"], ["Napa", "Ace"])
        self.assertEqual(chart["data"], [2, 1])

    def test_timeline_chart_uses_approval_timestamps_when_available(self):
        first_day = timezone.now() - timedelta(days=2)
        second_day = timezone.now() - timedelta(days=1)
        self.create_medicine("First Approval", status="verified", verified_at=first_day)
        self.create_medicine("Second Approval", status="sold", completed_at=timezone.now(), verified_at=second_day)
        self.create_medicine("No Approval Timestamp", status="verified", verified_at=None)

        chart = self.chart_by_title(get_dashboard_charts(), "Timeline")

        self.assertEqual(chart["labels"], [first_day.date().isoformat(), second_day.date().isoformat()])
        self.assertEqual(chart["data"], [1, 1])

    def test_timeline_chart_is_omitted_without_approval_timestamps(self):
        self.create_medicine("Approved Without Timestamp", status="verified", verified_at=None)

        chart_titles = [chart["title"] for chart in get_dashboard_charts()["charts"]]

        self.assertNotIn("Timeline", chart_titles)

    def test_empty_dashboard_chart_data(self):
        charts = get_dashboard_charts()

        self.assertFalse(charts["has_data"])
        self.assertEqual(charts["charts"], [])

    def test_dashboard_page_renders(self):
        self.seed_dashboard_medicines()

        response = self.client.get(reverse("impact_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Impact Dashboard")
        self.assertContains(response, "Medicines Donated")
        self.assertContains(response, "Active Marketplace Listings")
        self.assertContains(response, "dashboard-chart-data")
        self.assertContains(response, "Verification Outcomes")
        self.assertContains(response, "https://cdn.jsdelivr.net/npm/chart.js")
        self.assertTrue(response.context["chart_data"]["has_data"])

    def test_empty_dashboard_page_renders_empty_state(self):
        response = self.client.get(reverse("impact_dashboard"))

        self.assertContains(response, "No impact data available yet.")
        self.assertContains(response, "No analytics available yet.")
        self.assertFalse(response.context["chart_data"]["has_data"])


class ImpactReportTests(TestCase):
    def setUp(self):
        self.donor = User.objects.create_user(
            username="private_donor",
            email="donor@example.com",
            password="pass12345",
            role=User.Role.DONOR,
            phone="01700000000",
        )
        self.patient = User.objects.create_user(
            username="private_patient",
            email="patient@example.com",
            password="pass12345",
            role=User.Role.PATIENT,
            phone="01800000000",
        )

    def create_medicine(
        self,
        name,
        status="pending",
        patient=None,
        completed_at=None,
        reserved_until=None,
        verified_at=None,
        rejected_at=None,
        qr=False,
        original_price=Decimal("100.00"),
    ):
        medicine = Medicine.objects.create(
            donor=self.donor,
            name=name,
            scientific_name=f"{name} Scientific",
            batch_number=f"REPORT-{name[:8]}",
            expiry_date="2028-05-20",
            original_price=original_price,
            status=status,
            patient=patient,
            completed_at=completed_at,
            reserved_until=reserved_until,
            verified_at=verified_at,
            rejected_at=rejected_at,
        )
        if qr:
            ensure_medicine_qr(medicine)
        return medicine

    def seed_report_medicines(self):
        now = timezone.now()
        self.create_medicine("Pending Report Med")
        self.create_medicine("Rejected Report Med", status="rejected", rejected_at=now)
        self.create_medicine("Available Report Med", status="verified", verified_at=now, qr=True)
        self.create_medicine(
            "Reserved Report Med",
            status="verified",
            patient=self.patient,
            reserved_until=now + timedelta(hours=1),
            verified_at=now,
            qr=True,
        )
        self.create_medicine(
            "Collected Report Med",
            status="sold",
            patient=self.patient,
            completed_at=now,
            verified_at=now,
            qr=True,
            original_price=Decimal("200.00"),
        )

    def assert_anonymous(self, text):
        self.assertNotIn("private_donor", text)
        self.assertNotIn("private_patient", text)
        self.assertNotIn("donor@example.com", text)
        self.assertNotIn("patient@example.com", text)
        self.assertNotIn("01700000000", text)
        self.assertNotIn("01800000000", text)

    def test_overall_report(self):
        self.seed_report_medicines()

        report = generate_overall_report()

        self.assertTrue(report["has_data"])
        self.assertIn("ReMedi has processed 5 donated medicines.", report["content"])
        self.assertIn("3 medicines were approved and 1 were rejected.", report["content"])
        self.assertIn("The approval rate is 60.00% and the collection rate is 33.33%.", report["content"])

    def test_weekly_report(self):
        self.seed_report_medicines()

        report = generate_weekly_report()

        self.assertTrue(report["has_data"])
        self.assertIn("3 medicines were approved during this period.", report["content"])
        self.assertIn("1 medicines were rejected during this period.", report["content"])
        self.assertIn("1 medicines were collected by patients during this period.", report["content"])

    def test_waste_report(self):
        self.seed_report_medicines()

        report = generate_waste_report()

        self.assertTrue(report["has_data"])
        self.assertIn("The estimated medicine waste prevented count is 3.", report["content"])
        self.assertIn("reduces avoidable medicine waste", report["content"])

    def test_affordability_report(self):
        self.seed_report_medicines()

        report = generate_affordability_report()

        self.assertTrue(report["has_data"])
        self.assertIn("The estimated affordability benefit from collected medicines is 140.00 BDT.", report["content"])
        self.assertIn("The collection rate is 33.33% of approved medicines.", report["content"])

    def test_csr_report(self):
        self.seed_report_medicines()

        report = generate_csr_report()

        self.assertTrue(report["has_data"])
        self.assertIn("supports circular healthcare goals", report["content"])
        self.assertIn("NGO, hospital, pharmacy partner, CSR, and ESG reporting", report["content"])

    def test_empty_database_report(self):
        report = generate_overall_report()

        self.assertFalse(report["has_data"])
        self.assertEqual(report["content"], "")

    def test_report_output_is_anonymous(self):
        self.seed_report_medicines()

        reports = [
            generate_overall_report(),
            generate_weekly_report(),
            generate_waste_report(),
            generate_affordability_report(),
            generate_csr_report(),
        ]

        for report in reports:
            self.assert_anonymous(report["content"])

    def test_printable_page_renders(self):
        self.seed_report_medicines()

        response = self.client.get(reverse("impact_reports"), {"type": "csr"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CSR / ESG Summary")
        self.assertContains(response, "window.print()")
        self.assertContains(response, "Download TXT")
        self.assertTrue(response.context["report"]["has_data"])

    def test_report_page_empty_state(self):
        response = self.client.get(reverse("impact_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No report data available yet.")

    def test_download_text_works(self):
        self.seed_report_medicines()

        response = self.client.get(reverse("impact_reports"), {"type": "overall", "download": "txt"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("attachment; filename=\"remedi-overall-impact-report.txt\"", response["Content-Disposition"])
        text = response.content.decode()
        self.assertIn("ReMedi has processed 5 donated medicines.", text)
        self.assert_anonymous(text)


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


class HackathonMediaServeTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_existing_image_can_be_served(self):
        image_path = Path(self.media_root) / "medicines" / "2026" / "07" / "demo.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"demo image bytes")

        response = self.client.get("/media/medicines/2026/07/demo.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"demo image bytes")

    def test_missing_image_returns_404(self):
        response = self.client.get("/media/medicines/2026/07/missing.jpg")

        self.assertEqual(response.status_code, 404)

    def test_path_traversal_attempts_are_rejected(self):
        response = self.client.get("/media/%2e%2e/db.sqlite3")

        self.assertEqual(response.status_code, 404)


class CloudinaryStorageConfigTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.media_root, ignore_errors=True)

    @override_settings(USE_CLOUDINARY_STORAGE=False, STORAGES=LOCAL_MEDIA_TEST_STORAGE)
    def test_local_fallback_storage_backend_is_used_when_cloudinary_disabled(self):
        self.assertIsInstance(storages["default"], FileSystemStorage)

    @override_settings(
        USE_CLOUDINARY_STORAGE=True,
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "remedi-demo",
            "API_KEY": "demo-key",
            "API_SECRET": "demo-secret",
        },
        STORAGES=CLOUDINARY_MEDIA_TEST_STORAGE,
    )
    def test_cloudinary_storage_backend_is_used_when_enabled(self):
        from cloudinary_storage.storage import MediaCloudinaryStorage

        self.assertIsInstance(storages["default"], MediaCloudinaryStorage)

    @override_settings(MEDIA_ROOT="", STORAGES=LOCAL_MEDIA_TEST_STORAGE)
    def test_local_medicine_image_url_uses_media_url(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            medicine = Medicine(medicine_image="medicines/2026/07/local.jpg")

            self.assertEqual(medicine.medicine_image.url, "/media/medicines/2026/07/local.jpg")

    @override_settings(
        USE_CLOUDINARY_STORAGE=True,
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "remedi-demo",
            "API_KEY": "demo-key",
            "API_SECRET": "demo-secret",
        },
        STORAGES=CLOUDINARY_MEDIA_TEST_STORAGE,
    )
    def test_cloudinary_medicine_image_url_uses_hosted_url(self):
        medicine = Medicine(medicine_image="medicines/2026/07/cloud.jpg")

        self.assertIn("res.cloudinary.com/remedi-demo", medicine.medicine_image.url)
        self.assertIn("medicines/2026/07/cloud.jpg", medicine.medicine_image.url)

    @override_settings(STORAGES=LOCAL_MEDIA_TEST_STORAGE)
    def test_existing_upload_flow_continues_with_local_storage(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            donor = User.objects.create_user(
                username="cloudinary_flow_donor",
                password="pass12345",
                role=User.Role.DONOR,
            )
            self.client.force_login(donor)

            response = self.client.post(
                reverse("donate_medicine"),
                {
                    "name": "Cloudinary Switch Test",
                    "batch_number": "CLOUDINARY-FLOW-001",
                    "expiry_date": "2028-05-20",
                    "original_price": "500.00",
                    "medicine_image": create_test_image("cloudinary-flow.png"),
                },
            )

            self.assertRedirects(response, reverse("marketplace"), fetch_redirect_response=False)
            medicine = Medicine.objects.get(batch_number="CLOUDINARY-FLOW-001")
            self.assertTrue(medicine.medicine_image)
            self.assertTrue(medicine.medicine_image.name.endswith(".jpg"))
            self.assertTrue(Path(medicine.medicine_image.path).is_file())
