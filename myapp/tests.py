from django.core.management import call_command
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import FileSystemStorage, storages
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
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
from .services.explanation import build_explanation
from .services.fallback import get_ocr_fallback_result
from .services.pipeline import evaluate_donation
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
