"""Deterministic safety screening helpers for donation review foundations."""

SAFETY_FIELDS = (
    "damaged_packaging",
    "tampered_seal",
    "unclear_expiry",
    "suspicious_condition",
    "low_image_quality",
)

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
    """Return deterministic safety flags without ML or external services."""
    ocr_result = ocr_result or {}
    text = _combined_text(ocr_result, image_file)

    return {
        "damaged_packaging": _contains_any(text, DAMAGED_PACKAGING_KEYWORDS),
        "tampered_seal": _contains_any(text, TAMPERED_SEAL_KEYWORDS),
        "unclear_expiry": _has_unclear_expiry(ocr_result, text),
        "suspicious_condition": _contains_any(text, SUSPICIOUS_CONDITION_KEYWORDS),
        "low_image_quality": _has_low_image_quality(image_file, text),
    }


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

    if not _clean_value(ocr_result.get("batch_number")):
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


def _clean_value(value):
    return str(value or "").strip()


def _risk_level(score):
    if score <= 30:
        return "Low"
    if score <= 60:
        return "Medium"
    return "High"
