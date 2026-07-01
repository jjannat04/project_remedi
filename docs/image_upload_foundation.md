# Image Upload Foundation

## Upload Flow

Donors can optionally attach a medicine package image from the existing donation page. The form uses `multipart/form-data`, the view passes `request.FILES` into `DonationForm`, and the saved `Medicine.medicine_image` file is stored under `medicines/%Y/%m/`.

The upload is optional. Existing donations without images continue to work.

## Image Processing

`myapp/services/image_processing.py` provides `compress_uploaded_image(image)`.

It:

- resizes very large images to fit within 1600 x 1600 pixels,
- preserves aspect ratio,
- normalizes orientation from EXIF data,
- stores a compressed JPEG copy,
- prepares a consistent image file for future Gemini OCR usage.

This foundation does not call Gemini, OCR, risk scoring, QR generation, APIs, or background workers.

## Media Configuration

Media files are configured with:

- `MEDIA_URL = "/media/"`
- `MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))`

During local development, Django serves uploaded media when `DEBUG=True`. Set this in `.env` for local development:

```text
DEBUG=True
```

## Render Persistent Disk Plan

For a future Render deployment with durable uploads, attach a persistent disk and set `MEDIA_ROOT` to the mounted path. The default `BASE_DIR / "media"` keeps local SQLite development simple, while the environment override remains PostgreSQL-compatible because only the file path is stored in the database.

## Future Gemini Integration Plan

Future OCR can read `Medicine.medicine_image` after upload and pass the compressed file to Gemini from a normal Django service function. That future integration should remain optional, deterministic in demo mode, and guarded so upload and donation flows continue to work if AI is unavailable.
