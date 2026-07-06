from django.core.management import call_command
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

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
from .services.fallback import get_ocr_fallback_result
from .services.safety import analyze_image_safety, calculate_donation_risk
from .services.demo_data import (
    DEMO_BATCH_PREFIX,
    DEMO_DONOR_EMAIL,
    DEMO_PATIENT_EMAIL,
    DEMO_PHARMACIST_EMAIL,
)


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

    @override_settings(
        GEMINI_API_KEY="demo-key",
        GEMINI_MODEL="gemini-first",
        GEMINI_FALLBACK_MODELS=["gemini-second"],
        OCR_SPACE_ENABLED=True,
        OCR_SPACE_API_KEY="ocr-key",
    )
    @patch("myapp.services.ai._generate_gemini_text", side_effect=FakeQuotaError("429 quota exceeded"))
    @patch(
        "myapp.services.ai._post_ocr_space",
        return_value='{"IsErroredOnProcessing":false,"ParsedResults":[{"ParsedText":"Napa Extra\\n500 mg"}]}',
    )
    def test_all_gemini_models_failing_then_tries_ocr_space(self, mock_ocr_space, mock_gemini):
        with self.assertLogs("myapp.services.ai", level="INFO"):
            result = analyze_medicine_image(fake_image_file())

        self.assertEqual(result["source"], "ocr_space")
        self.assertEqual(result["message"], OCR_SPACE_AFTER_GEMINI_MESSAGE)
        self.assertEqual(mock_gemini.call_count, 2)
        self.assertEqual(mock_ocr_space.call_count, 1)

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

    @override_settings(GEMINI_API_KEY="", OCR_SPACE_ENABLED=True, OCR_SPACE_API_KEY="ocr-key")
    @patch("myapp.services.ai._post_ocr_space", side_effect=OSError("network unavailable"))
    def test_ocr_space_unavailable_uses_fallback_json(self, _mock_ocr_space):
        with self.assertLogs("myapp.services.ai", level="INFO"):
            result = analyze_medicine_image(fake_image_file())

        self.assertEqual(result["source"], "fallback")
        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["message"], MISSING_API_KEY_MESSAGE)

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

    @override_settings(GEMINI_API_KEY="", OCR_SPACE_ENABLED=True, OCR_SPACE_API_KEY="ocr-key")
    @patch(
        "myapp.services.ai._post_ocr_space",
        return_value='{"IsErroredOnProcessing":false,"ParsedResults":[{"ParsedText":"Napa Extra\\n500 mg"}]}',
    )
    def test_cache_hit_skips_ocr_space_request(self, mock_ocr_space):
        with self.assertLogs("myapp.services.ai", level="INFO"):
            first = analyze_medicine_image(fake_image_file())
            second = analyze_medicine_image(fake_image_file())

        self.assertEqual(first, second)
        self.assertEqual(first["source"], "ocr_space")
        self.assertEqual(mock_ocr_space.call_count, 1)

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

    @override_settings(DEMO_MODE=True, GEMINI_API_KEY="", OCR_SPACE_ENABLED=False, OCR_SPACE_API_KEY="")
    def test_ocr_page_works_in_demo_mode(self):
        with self.assertLogs("myapp.services.ai", level="WARNING"):
            response = self.client.post(
                reverse("judge_ocr"),
                {"medicine_image": fake_image_file()},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Extracted JSON")
        self.assertContains(response, "fallback")
        self.assertContains(response, MISSING_API_KEY_MESSAGE)

    @override_settings(
        DEMO_MODE=True,
        GEMINI_API_KEY="demo-key",
        GEMINI_MODEL="gemini-test",
        GEMINI_FALLBACK_MODELS=[],
        OCR_SPACE_ENABLED=False,
        OCR_SPACE_API_KEY="",
    )
    @patch("myapp.services.ai._generate_gemini_text", side_effect=FakeQuotaError("429 quota exceeded"))
    def test_ocr_page_returns_200_and_json_during_quota_failure(self, _mock_generate):
        with self.assertLogs("myapp.services.ai", level="INFO"):
            response = self.client.post(
                reverse("judge_ocr"),
                {"medicine_image": fake_image_file()},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, QUOTA_FALLBACK_MESSAGE)
        self.assertContains(response, "Extracted JSON")
        self.assertContains(response, "&quot;source&quot;: &quot;fallback&quot;")
        self.assertContains(response, "&quot;used_fallback&quot;: true")
