"""Deterministic explanation helpers for AI donation evaluations."""


def build_explanation(evaluation):
    """Build a human-readable explanation from a pipeline evaluation."""
    evaluation = evaluation or {}
    ocr = evaluation.get("ocr") or {}
    safety = evaluation.get("safety") or {}
    risk = evaluation.get("risk") or {}
    decision = evaluation.get("decision") or {}

    positive_points = _positive_points(ocr, safety, risk)
    negative_points = _negative_points(ocr, safety, risk)

    return {
        "title": _title(decision),
        "summary": _summary(ocr, safety, risk, decision),
        "highlights": positive_points + negative_points,
        "positive_points": positive_points,
        "negative_points": negative_points,
    }


def _title(decision):
    decision_value = (decision.get("decision") or "").lower()
    if decision_value == "accept":
        return "Medicine appears suitable for donation"
    if decision_value == "review":
        return "Manual review recommended"
    if decision_value == "reject":
        return "Medicine should not be donated"
    return "AI evaluation complete"


def _summary(ocr, safety, risk, decision):
    identified = "The uploaded medicine was successfully identified."
    if not (ocr.get("medicine_name") or "").strip():
        identified = "The uploaded medicine could not be clearly identified."

    packaging = "No signs of damaged packaging were detected."
    if safety.get("damaged_packaging") or safety.get("tampered_seal"):
        packaging = "Packaging or seal concerns were detected."

    risk_level = (risk.get("risk_level") or "unknown").lower()
    decision_value = (decision.get("decision") or "review").lower()
    return (
        f"{identified} {packaging} The overall risk score is {risk_level}, "
        f"therefore the recommendation is {decision_value}."
    )


def _positive_points(ocr, safety, risk):
    points = []
    if (ocr.get("medicine_name") or "").strip():
        points.append("Medicine identified successfully")
    if not safety.get("damaged_packaging") and not safety.get("tampered_seal"):
        points.append("Packaging appears intact")
    if (ocr.get("expiry_text") or "").strip() and not safety.get("unclear_expiry"):
        points.append("Expiry information detected")
    if _confidence(ocr) >= 0.8:
        points.append("OCR confidence is high")
    if _risk_score(risk) <= 30:
        points.append("Risk score is low")
    return points


def _negative_points(ocr, safety, risk):
    points = []
    if safety.get("low_image_quality"):
        points.append("Low image quality detected")
    if not (ocr.get("batch_number") or "").strip():
        points.append("Batch number missing")
    if safety.get("tampered_seal"):
        points.append("Tampered seal detected")
    if safety.get("damaged_packaging"):
        points.append("Damaged packaging detected")
    if safety.get("unclear_expiry") or not (ocr.get("expiry_text") or "").strip():
        points.append("Expiry information unclear or missing")
    if safety.get("suspicious_condition"):
        points.append("Suspicious condition detected")
    if _confidence(ocr) < 0.8:
        points.append("OCR confidence is low")
    if _risk_score(risk) >= 70:
        points.append("Risk score is high")
    return points


def _confidence(ocr):
    try:
        return float(ocr.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _risk_score(risk):
    try:
        return int(risk.get("risk_score", 0))
    except (TypeError, ValueError):
        return 0
