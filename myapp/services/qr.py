"""QR helpers for secure medicine traceability."""

import base64
from io import BytesIO
import secrets

from django.utils import timezone


QR_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_qr_identifier():
    """Return a human-readable, hard-to-guess public QR identifier."""
    groups = [
        "".join(secrets.choice(QR_ALPHABET) for _ in range(4))
        for _ in range(3)
    ]
    return f"RMD-{'-'.join(groups)}"


def qr_payload(qr_code_id):
    """Return the exact public payload encoded into a QR code."""
    return (qr_code_id or "").strip().upper()


def ensure_medicine_qr(medicine):
    """Ensure an approved medicine has a stable public QR identifier."""
    if medicine.qr_code_id:
        return medicine

    from myapp.models import Medicine

    qr_code_id = generate_qr_identifier()
    while Medicine.objects.filter(qr_code_id=qr_code_id).exists():
        qr_code_id = generate_qr_identifier()

    medicine.qr_code_id = qr_code_id
    medicine.qr_generated_at = timezone.now()
    medicine.save(update_fields=["qr_code_id", "qr_generated_at"])
    return medicine


def render_qr_data_uri(qr_code_id):
    """Render a printable QR PNG data URI containing only the public QR ID."""
    import qrcode

    image = qrcode.make(qr_payload(qr_code_id))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def lookup_qr(qr_code_id):
    """Resolve a public QR ID to medicine, donation, and donor server-side."""
    from myapp.models import Medicine

    medicine = Medicine.objects.select_related("donor").get(qr_code_id=qr_payload(qr_code_id))
    return {
        "medicine": medicine,
        "donation": medicine,
        "donor": medicine.donor,
    }
