# Gemini OCR Foundation

## Architecture

The OCR foundation lives in the existing Django app and keeps all Gemini access inside service-layer functions:

- `myapp/services/ai.py` exposes `analyze_medicine_image(image_file)` and `analyze_with_ocr_space(image_file)`.
- `myapp/services/fallback.py` owns deterministic fallback output.
- `myapp/services/cache.py` hashes image bytes and caches OCR results.

The temporary `/judge/ocr/` page is server-rendered and only calls the service function. It does not change the donation flow, pharmacist workflow, marketplace, QR logic, OTP, or database schema.

## Environment Variables

```text
GEMINI_API_KEY=your-api-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-2.5-flash,gemini-2.5-flash-lite
OCR_SPACE_API_KEY=your-ocr-space-api-key
OCR_SPACE_ENABLED=True
AI_FALLBACK_ENABLED=True
```

`GEMINI_API_KEY` is required for Gemini OCR. `GEMINI_MODEL` selects the primary Gemini model, and `GEMINI_FALLBACK_MODELS` is a comma-separated list of additional Gemini models to try before leaving Gemini. `OCR_SPACE_API_KEY` enables the temporary OCR.space fallback provider when Gemini is unavailable or over quota.

## Provider Chain

The OCR flow is:

1. Hash the uploaded image bytes and check the OCR cache.
2. Try Gemini first when `GEMINI_API_KEY` exists, using `GEMINI_MODEL` followed by any unique models in `GEMINI_FALLBACK_MODELS`.
3. If all configured Gemini models fail because of quota, API errors, network errors, invalid JSON, or other exceptions, try OCR.space when `OCR_SPACE_ENABLED=True` and `OCR_SPACE_API_KEY` exists.
4. If OCR.space also fails or is not configured, return deterministic fallback JSON.

OCR.space output is converted into the same result shape using lightweight regex heuristics for dosage, batch number, expiry text, and manufacturer. Requests include `language=eng`, `isOverlayRequired=false`, `scale=true`, `detectOrientation=true`, and `OCREngine=2` to improve text extraction from clear packaging photos. It is a temporary hackathon continuity provider, not a replacement for reviewed OCR.

If OCR.space returns a successful response but no readable `ParsedText`, the service returns deterministic fallback JSON with the message:

```text
OCR.space could not read text from this image. Showing deterministic fallback output.
```

## Fallback Philosophy

OCR must never block the demo. If Gemini and OCR.space are unavailable, misconfigured, or return invalid responses, the service returns:

```json
{
  "medicine_name": "",
  "scientific_name": "",
  "dosage": "",
  "manufacturer": "",
  "batch_number": "",
  "expiry_text": "",
  "confidence": 0.0,
  "source": "fallback",
  "used_fallback": true,
  "message": "..."
}
```

## Cache Strategy

The uploaded image bytes are hashed with SHA-256. OCR results are cached under that hash for 24 hours. Re-analyzing the same image returns the cached dictionary and avoids another Gemini call.

## Limitations

The prompt asks Gemini to analyze only medicine packaging images, extract visible text only, never invent information, and return JSON only. The service validates the JSON shape and confidence range, but it does not yet prefill forms, score risk, verify authenticity, or persist OCR output.

## Future Integration Plan

Future phases can call `analyze_medicine_image()` from the donation flow to suggest form values after image upload. That integration should remain optional, reviewable by the donor, and fallback-safe.
