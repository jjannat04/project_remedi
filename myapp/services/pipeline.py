"""Donation AI evaluation pipeline orchestration."""

from typing import Any

from myapp.services.ai import analyze_medicine_image
from myapp.services.decision import make_ai_decision
from myapp.services.safety import analyze_image_safety, calculate_donation_risk


def evaluate_donation(image_file: Any) -> dict:
    """Evaluate a donation image through OCR, safety, risk, and decision steps."""
    ocr_result = analyze_medicine_image(image_file)
    safety_result = analyze_image_safety(image_file, ocr_result)
    risk_result = calculate_donation_risk(ocr_result, safety_result)
    decision_result = make_ai_decision(ocr_result, safety_result, risk_result)

    return {
        "ocr": ocr_result,
        "safety": safety_result,
        "risk": risk_result,
        "decision": decision_result,
    }
