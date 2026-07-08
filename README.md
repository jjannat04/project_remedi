# ReMedi - Circular Healthcare Redistribution Platform

Live Link: https://project-remedi.onrender.com

ReMedi is a Django-based circular healthcare platform that helps reduce medicine waste and improve affordable access to essential medicines. Donors can upload unused, unexpired medicines, AI-assisted checks can extract and assess package information, licensed pharmacists make the final verification decision, and patients can reserve verified medicines for secure pickup.

The platform is built for the Bangladesh healthcare context and includes marketplace listings, pharmacist review workflows, QR traceability, OTP-based pickup confirmation, impact dashboards, reports, and demo utilities for realistic presentation data.

## Core Features

- Public medicine marketplace for verified, available medicines.
- Donor medicine submission with medicine name, generic name, dosage, manufacturer, expiry, quantity, location, package details, and image upload.
- Image compression for uploaded medicine package photos.
- AI-assisted donation analysis using OCR and visual safety checks.
- Gemini OCR and safety analysis support, with OCR.space and deterministic fallback paths for demo reliability.
- Risk scoring and donation decision support for pharmacist review.
- Licensed pharmacist verification queue for pending donations.
- Human-in-the-loop final review with approve/reject actions.
- Rejection reasons and rejection timestamps for unsafe donations.
- Approval timestamps and QR identifiers for verified medicines.
- Secure QR traceability for approved medicines.
- Patient reservation flow for marketplace medicines.
- Pickup OTP generation for reserved medicines.
- Pharmacist pickup desk for QR/medicine ID plus OTP verification.
- Completed pickup flow that marks medicines as collected/sold.
- Donor and patient profile pages showing donations, reservations, and completed orders.
- Impact dashboard with donation, verification, rejection, reservation, collection, waste prevention, and patients helped metrics.
- Chart-based dashboard visualizations for verification outcomes, marketplace distribution, risk levels, medicine categories, and approval timeline.
- Downloadable text impact reports for overall, weekly, waste prevention, affordability, and CSR/ESG summaries.
- ReMedi Corner map for pickup/collection points.
- Demo mode with judge-friendly login paths and deterministic demo users.
- One-time historical demo population command for realistic dashboard and report metrics without modifying existing marketplace medicines.
- Cloudinary support for durable hosted medicine images in deployment.
- Render-ready deployment setup with WhiteNoise static files and PostgreSQL support through `DATABASE_URL`.

## Main Workflows

### Donor Workflow

1. A donor signs up or logs in.
2. The donor submits medicine details and uploads a package image.
3. The donation enters pending review.
4. AI-assisted OCR and safety checks can help summarize package details and risk signals.
5. A pharmacist makes the final decision.
6. The donor can track pending, verified, reserved, rejected, and sold donations from the profile page.

### Pharmacist Workflow

1. A licensed pharmacist logs in.
2. The pharmacist reviews pending medicines from the verification center.
3. Approved medicines receive verification metadata and QR traceability.
4. Rejected medicines receive a rejection reason and timestamp.
5. At pickup time, the pharmacist uses the pickup desk to verify the patient-held OTP against the QR ID or medicine ID.

### Patient Workflow

1. A patient browses verified medicines in the marketplace.
2. The patient reserves an available medicine.
3. The system issues a pickup OTP.
4. The patient presents the OTP at collection.
5. A pharmacist verifies the pickup and marks the medicine as collected.

## Tech Stack

- Backend: Django 6
- Language: Python
- Database: SQLite for local development, PostgreSQL-ready via `DATABASE_URL`
- Frontend: Django templates, Tailwind CDN, Bootstrap Icons
- Static files: WhiteNoise
- Media storage: Local filesystem or Cloudinary
- AI/OCR: Google Gemini, OCR.space fallback, deterministic fallback
- Image processing: Pillow
- QR codes: `qrcode`
- Deployment: Render, Gunicorn

## Important Pages

- Marketplace: `/` or `/marketplace/`
- Medicine details: `/marketplace/<medicine_id>/`
- Donate medicine: `/donate/`
- AI image analysis endpoint: `/donate/analyze/`
- Profile: `/profile/`
- Pharmacist verification queue: `/pharmacist/queue/`
- Pharmacist review page: `/pharmacist/review/<medicine_id>/`
- Pharmacist pickup desk: `/pharmacist/pickup/`
- Impact dashboard: `/dashboard/`
- Impact reports: `/reports/`
- ReMedi Corner map: `/map/`
- Judge demo entry: `/judge/`

## Local Setup

### 1. Clone The Repository

```bash
git clone <your-repo-link>
cd Project_Remedi
```

### 2. Create And Activate A Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root. For local development, this minimal setup is enough:

```env
DEBUG=True
DEMO_MODE=True
AI_FALLBACK_ENABLED=True
USE_CLOUDINARY_STORAGE=False
```

Optional AI/OCR configuration:

```env
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-2.5-flash,gemini-2.5-flash-lite
OCR_SPACE_API_KEY=your-ocr-space-api-key
OCR_SPACE_ENABLED=True
```

Optional Cloudinary configuration:

```env
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
USE_CLOUDINARY_STORAGE=True
```

### 5. Apply Migrations

```bash
python manage.py migrate
```

### 6. Create An Admin User

```bash
python manage.py createsuperuser
```

### 7. Run The Development Server

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

## Demo Data Commands

ReMedi includes demo utilities for presentations and testing.

Create or refresh the main deterministic demo dataset:

```bash
python manage.py seed_demo
```

Reset and recreate the deterministic demo dataset:

```bash
python manage.py reset_demo
```

Create one-time historical demo records for realistic dashboard/report metrics:

```bash
python manage.py populate_demo_history
```

Notes:

- `populate_demo_history` is not a reset command.
- It does not delete existing data.
- It does not modify manually added marketplace medicines or images.
- It exits safely if historical demo records already exist.
- Historical verified records are completed/sold records, so they do not appear as active marketplace inventory.

## Running Checks And Tests

Run Django system checks:

```bash
python manage.py check
```

Run the test suite:

```bash
python manage.py test
```

Run a focused reservation/pickup test group:

```bash
python manage.py test myapp.tests.ReservationSystemTests
```

## Deployment Notes

The project includes a Render-compatible `build.sh`:

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
```

Recommended Render settings:

- Build Command: `./build.sh`
- Start Command: `gunicorn remedi.wsgi:application`
- Set `DATABASE_URL` for PostgreSQL.
- Set `SECRET_KEY` in production.
- Set `DEBUG=False`.
- Set `DEMO_MODE=True` only for demo/judging environments.
- Use Cloudinary for durable uploaded medicine images on Render.

To auto-populate historical demo metrics during Render builds, add this after migrations in `build.sh`:

```bash
python manage.py populate_demo_history
```

Because the command is idempotent, repeated deploys will not duplicate historical records.

## Environment Variables

Common variables:

```env
SECRET_KEY=your-production-secret
DEBUG=False
DEMO_MODE=False
DATABASE_URL=postgres://...
ALLOWED_HOSTS=project-remedi.onrender.com
MEDIA_ROOT=/path/to/media
```

AI/OCR variables:

```env
AI_FALLBACK_ENABLED=True
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-2.5-flash,gemini-2.5-flash-lite
OCR_SPACE_API_KEY=your-ocr-space-api-key
OCR_SPACE_ENABLED=True
```

Cloudinary variables:

```env
USE_CLOUDINARY_STORAGE=True
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
```

Production security variables supported by settings:

```env
PRODUCTION=True
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

## Project Structure

```text
Project_Remedi/
|-- manage.py
|-- requirements.txt
|-- build.sh
|-- remedi/
|   |-- settings.py
|   |-- urls.py
|   `-- wsgi.py
|-- myapp/
|   |-- models.py
|   |-- views.py
|   |-- urls.py
|   |-- forms.py
|   |-- services/
|   |-- management/commands/
|   |-- templates/myapp/
|   `-- tests.py
|-- docs/
|-- media/
`-- staticfiles/
```

## Safety And Trust Model

ReMedi is designed around a human-final-decision workflow:

- AI assists with OCR, package analysis, and risk signals.
- Pharmacists make the final approval or rejection decision.
- Verified medicines receive QR traceability.
- Patient pickup requires an OTP held by the patient.
- Unsafe, damaged, expired, or unclear medicines can be rejected with a recorded reason.

## Future Improvements

- Add richer pharmacist audit logs.
- Add notification flows for reservation and pickup updates.
- Add role-specific admin dashboards.
- Add stronger reporting exports such as PDF or CSV.
- Add persistent production media storage by default.
- Add more granular medicine category analytics.

## Screenshots

Add final screenshots here before submission.

### Marketplace

![Marketplace screenshot placeholder](docs/screenshots/marketplace-placeholder.png)

### Donation Flow

![Donation flow screenshot placeholder](docs/screenshots/donation-placeholder.png)

### Pharmacist Verification Queue

![Pharmacist queue screenshot placeholder](docs/screenshots/pharmacist-queue-placeholder.png)

### Pickup Verification Desk

![Pickup verification screenshot placeholder](docs/screenshots/pickup-placeholder.png)

### Impact Dashboard

![Impact dashboard screenshot placeholder](docs/screenshots/dashboard-placeholder.png)
