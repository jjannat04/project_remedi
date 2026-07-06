"""Deterministic donation decision helpers for AI-assisted review foundations."""

ACCEPT_DECISION = "accept"
REVIEW_DECISION = "review"
REJECT_DECISION = "reject"

ACCEPT_CONFIDENCE = 0.90
REVIEW_CONFIDENCE = 0.65
REJECT_CONFIDENCE = 0.95


def make_ai_decision(ocr_result, safety_result, risk_result):
    """Return an explainable decision without model calls or randomness."""
    ocr_result = ocr_result or {}
    safety_result = safety_result or {}
    risk_result = risk_result or {}

    risk_score = _risk_score(risk_result)
    ocr_confidence = _ocr_confidence(ocr_result)

    reject_reasons = _reject_reasons(risk_score, safety_result)
    if reject_reasons:
        return _decision(REJECT_DECISION, REJECT_CONFIDENCE, reject_reasons)

    review_reasons = _review_reasons(risk_score, safety_result, ocr_confidence)
    if review_reasons:
        return _decision(REVIEW_DECISION, REVIEW_CONFIDENCE, review_reasons)

    return _decision(
        ACCEPT_DECISION,
        ACCEPT_CONFIDENCE,
        ["Risk is low, no safety issues were detected, and OCR confidence is acceptable."],
    )


def _reject_reasons(risk_score, safety_result):
    reasons = []
    if risk_score >= 70:
        reasons.append("Risk score is 70 or higher.")
    if safety_result.get("tampered_seal"):
        reasons.append("Tampered seal was detected.")
    if safety_result.get("damaged_packaging"):
        reasons.append("Damaged packaging was detected.")
    return reasons


def _review_reasons(risk_score, safety_result, ocr_confidence):
    reasons = []
    if 31 <= risk_score <= 69:
        reasons.append("Risk score is between 31 and 69.")
    if safety_result.get("unclear_expiry"):
        reasons.append("Expiry is unclear.")
    if ocr_confidence < 0.8:
        reasons.append("OCR confidence is below 0.8.")
    return reasons


def _decision(decision, confidence, reasons):
    return {
        "decision": decision,
        "confidence": confidence,
        "reasons": reasons,
    }


def _risk_score(risk_result):
    try:
        return int(risk_result.get("risk_score", 0))
    except (TypeError, ValueError):
        return 0


def _ocr_confidence(ocr_result):
    try:
        return float(ocr_result.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0
