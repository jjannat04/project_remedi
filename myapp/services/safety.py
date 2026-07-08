"""AI-assisted visual safety screening with deterministic fallback."""

import json
import logging

from django.conf import settings

from myapp.services.cache import read_file_bytes


logger = logging.getLogger(__name__)

SAFETY_FIELDS = (
    "damaged_packaging",
    "tampered_seal",
    "unclear_expiry",
    "suspicious_condition",
    "low_image_quality",
)

GEMINI_SAFETY_REQUIRED_FIELDS = (
    "damaged_packaging",
    "tampered_seal",
    "unclear_expiry",
    "missing_batch",
    "suspicious_condition",
    "low_image_quality",
    "counterfeit_warning",
    "confidence",
    "summary",
)

GEMINI_SAFETY_OPTIONAL_BOOL_FIELDS = (
    "torn_packaging",
    "missing_safety_seal",
    "blurry_expiry",
    "blurry_batch_number",
    "water_damage",
    "moisture_damage",
    "crushed_strip",
    "broken_bottle",
    "missing_label",
    "image_unsuitable",
)

GEMINI_SAFETY_PROMPT = """
Inspect only the visual condition of the medicine package image.
Do not diagnose, identify disease, judge clinical suitability, or decide approval.
You are assisting a pharmacist by reporting visible package-safety findings only.

Look for: damaged packaging, torn packaging, broken or tampered seal, missing safety
seal, blurry or unreadable expiry, blurry batch number, water or moisture damage,
crushed strip, broken bottle, suspicious package condition, missing medicine label,
visually obvious counterfeit warning signs, poor image quality, and whether the image
is unsuitable for verification.

Return JSON only with these keys:
damaged_packaging, tampered_seal, unclear_expiry, missing_batch,
suspicious_condition, low_image_quality, counterfeit_warning, confidence, summary,
torn_packaging, missing_safety_seal, blurry_expiry, blurry_batch_number,
water_damage, moisture_damage, crushed_strip, broken_bottle, missing_label,
image_unsuitable.

Boolean keys must be true or false.
confidence must be a number between 0 and 1.
summary must be one short sentence describing the visual findings.
"""

DAMAGED_PACKAGING_KEYWORDS = (
    "damaged",
    "damage",
    "torn",
    "crushed",
    "broken",
    "leak",
    "leaked",
    "wet",
)

TAMPERED_SEAL_KEYWORDS = (
    "tamper",
    "tampered",
    "seal broken",
    "seal open",
    "opened seal",
    "opened",
)

UNCLEAR_EXPIRY_KEYWORDS = (
    "unclear expiry",
    "expiry unclear",
    "illegible expiry",
    "missing expiry",
)

SUSPICIOUS_CONDITION_KEYWORDS = (
    "counterfeit",
    "fake",
    "suspicious",
    "mismatch",
    "unsealed",
)

LOW_IMAGE_QUALITY_KEYWORDS = (
    "blur",
    "blurry",
    "dark",
    "low quality",
    "unreadable",
)

LOW_IMAGE_SIZE_BYTES = 1024


def analyze_image_safety(image_file, ocr_result):
    """Return visual safety findings from Gemini Vision with deterministic fallback."""
    if getattr(settings, "GEMINI_API_KEY", ""):
        for attempt in range(2):
            try:
                response_text = _generate_gemini_safety_text(image_file)
                result = _parse_gemini_safety_json(response_text)
                return result
            except Exception:
                logger.warning("Gemini visual safety inspection failed on attempt %s.", attempt + 1)

    try:
        return analyze_image_safety_deterministic(image_file, ocr_result)
    except Exception:
        logger.exception("Deterministic safety fallback failed.")
        return _safe_fallback_result()


def analyze_image_safety_deterministic(image_file, ocr_result):
    """Return deterministic visual safety flags without external services."""
    ocr_result = ocr_result or {}
    text = _combined_text(ocr_result, image_file)
    result = {
        "damaged_packaging": _contains_any(text, DAMAGED_PACKAGING_KEYWORDS),
        "tampered_seal": _contains_any(text, TAMPERED_SEAL_KEYWORDS),
        "unclear_expiry": _has_unclear_expiry(ocr_result, text),
        "missing_batch": not _clean_value(ocr_result.get("batch_number")),
        "suspicious_condition": _contains_any(text, SUSPICIOUS_CONDITION_KEYWORDS),
        "low_image_quality": _has_low_image_quality(image_file, text),
        "counterfeit_warning": _contains_any(text, ("counterfeit", "fake")),
        "confidence": 0.55,
        "summary": "Deterministic fallback safety screening completed.",
        "source": "deterministic",
    }
    return _normalize_safety_result(result)


def calculate_donation_risk(ocr_result, safety_result):
    ocr_result = ocr_result or {}
    safety_result = safety_result or {}
    score = 0
    reasons = []

    if safety_result.get("unclear_expiry") or not _clean_value(ocr_result.get("expiry_text")):
        score += 30
        reasons.append("Expiry is unclear or missing.")

    if _confidence_value(ocr_result.get("confidence")) < 0.8:
        score += 20
        reasons.append("OCR confidence is below 0.8.")

    if safety_result.get("missing_batch") or not _clean_value(ocr_result.get("batch_number")):
        score += 20
        reasons.append("Batch number is missing.")

    if safety_result.get("tampered_seal"):
        score += 30
        reasons.append("Tampering or seal issue detected.")

    score = min(score, 100)

    return {
        "risk_score": score,
        "risk_level": _risk_level(score),
        "reasons": reasons,
    }


def _generate_gemini_safety_text(image_file):
    from google import genai
    from google.genai import types

    image_bytes = read_file_bytes(image_file)
    mime_type = getattr(image_file, "content_type", None) or "image/jpeg"
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
        contents=[
            GEMINI_SAFETY_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
    )
    return response.text


def _parse_gemini_safety_json(response_text):
    parsed = json.loads(_strip_json_markdown_fence(response_text))
    if not isinstance(parsed, dict):
        raise ValueError("Gemini safety response must be a JSON object.")

    for field in GEMINI_SAFETY_REQUIRED_FIELDS:
        if field not in parsed:
            raise ValueError(f"Gemini safety response is missing {field}.")

    result = {}
    for field in GEMINI_SAFETY_REQUIRED_FIELDS:
        if field == "confidence":
            confidence = float(parsed[field])
            if confidence < 0 or confidence > 1:
                raise ValueError("Gemini safety confidence must be between 0 and 1.")
            result[field] = confidence
        elif field == "summary":
            summary = str(parsed[field] or "").strip()
            if not summary:
                raise ValueError("Gemini safety summary is required.")
            result[field] = summary
        else:
            if not isinstance(parsed[field], bool):
                raise ValueError(f"Gemini safety field {field} must be boolean.")
            result[field] = parsed[field]

    for field in GEMINI_SAFETY_OPTIONAL_BOOL_FIELDS:
        result[field] = bool(parsed.get(field, False))

    result["source"] = "gemini"
    return _normalize_safety_result(result)


def _normalize_safety_result(result):
    result = result or {}
    normalized = {
        "damaged_packaging": bool(result.get("damaged_packaging")),
        "tampered_seal": bool(result.get("tampered_seal")),
        "unclear_expiry": bool(result.get("unclear_expiry")),
        "missing_batch": bool(result.get("missing_batch")),
        "suspicious_condition": bool(result.get("suspicious_condition")),
        "low_image_quality": bool(result.get("low_image_quality")),
        "counterfeit_warning": bool(result.get("counterfeit_warning")),
        "confidence": _bounded_confidence(result.get("confidence")),
        "summary": str(result.get("summary") or "Visual safety screening completed.").strip(),
        "source": result.get("source") or "fallback",
    }
    for field in GEMINI_SAFETY_OPTIONAL_BOOL_FIELDS:
        normalized[field] = bool(result.get(field))
    normalized["package_intact"] = not normalized["damaged_packaging"]
    normalized["seal_valid"] = not normalized["tampered_seal"] and not normalized["missing_safety_seal"]
    normalized["label_readable"] = not normalized["missing_label"] and not normalized["image_unsuitable"]
    normalized["warnings"] = _safety_warnings(normalized)
    return normalized


def _safe_fallback_result():
    return _normalize_safety_result({
        "low_image_quality": True,
        "unclear_expiry": True,
        "missing_batch": True,
        "confidence": 0.0,
        "summary": "Safety inspection could not complete; pharmacist review is required.",
        "source": "safe_fallback",
    })


def _safety_warnings(safety):
    warnings = []
    if safety.get("unclear_expiry"):
        warnings.append("Expiry text is blurry or unclear")
    if safety.get("missing_batch"):
        warnings.append("Batch number is missing or unreadable")
    if safety.get("low_image_quality"):
        warnings.append("Image quality is low")
    if safety.get("damaged_packaging"):
        warnings.append("Possible package damage")
    if safety.get("tampered_seal"):
        warnings.append("Possible broken or tampered seal")
    if safety.get("counterfeit_warning"):
        warnings.append("Visually obvious counterfeit warning signs")
    if safety.get("image_unsuitable"):
        warnings.append("Image unsuitable for verification")
    return warnings


def _strip_json_markdown_fence(response_text):
    text = (response_text or "").strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines and lines[0].strip().lower() in {"```json", "```"}:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _combined_text(ocr_result, image_file):
    values = []
    for value in (ocr_result or {}).values():
        if isinstance(value, str):
            values.append(value)
    filename = getattr(image_file, "name", "")
    if filename:
        values.append(filename)
    return " ".join(values).lower()


def _contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def _has_unclear_expiry(ocr_result, text):
    expiry_text = _clean_value((ocr_result or {}).get("expiry_text"))
    return not expiry_text or _contains_any(text, UNCLEAR_EXPIRY_KEYWORDS)


def _has_low_image_quality(image_file, text):
    content_type = getattr(image_file, "content_type", "") or ""
    if content_type and not content_type.startswith("image/"):
        return True

    image_size = getattr(image_file, "size", None)
    if image_size is not None and image_size < LOW_IMAGE_SIZE_BYTES:
        return True

    return _contains_any(text, LOW_IMAGE_QUALITY_KEYWORDS)


def _confidence_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bounded_confidence(value):
    confidence = _confidence_value(value)
    return min(max(confidence, 0.0), 1.0)


def _clean_value(value):
    return str(value or "").strip()


def _risk_level(score):
    if score <= 30:
        return "Low"
    if score <= 60:
        return "Medium"
    return "High"
