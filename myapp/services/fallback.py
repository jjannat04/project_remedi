"""Fallback helpers for resilient demo and AI behavior."""


OCR_FALLBACK_RESULT = {
    "medicine_name": "",
    "scientific_name": "",
    "dosage": "",
    "manufacturer": "",
    "batch_number": "",
    "expiry_text": "",
    "confidence": 0.0,
    "source": "fallback",
    "used_fallback": True,
    "message": "Showing deterministic fallback output.",
}


def get_ocr_fallback_result(message=None):
    result = OCR_FALLBACK_RESULT.copy()
    if message:
        result["message"] = message
    return result
