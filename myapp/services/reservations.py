"""Reservation and pickup OTP workflow for marketplace medicines."""

import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from myapp.models import Medicine


RESERVATION_DURATION = timedelta(hours=24)


def generate_pickup_otp():
    """Return a random six-digit pickup OTP."""
    return f"{secrets.randbelow(1000000):06d}"


def release_expired_reservations(now=None):
    """Release verified medicines whose active reservation window has expired."""
    now = now or timezone.now()
    return (
        Medicine.objects
        .filter(status="verified", patient__isnull=False, completed_at__isnull=True, reserved_until__lte=now)
        .update(patient=None, ordered_at=None, reserved_until=None, pickup_otp="", otp_generated_at=None)
    )


def get_active_reserved_pickups(now=None):
    """Return active reserved medicines visible to pickup verifiers."""
    now = now or timezone.now()
    release_expired_reservations(now)
    return (
        Medicine.objects
        .select_related("patient", "donor")
        .filter(
            status="verified",
            patient__isnull=False,
            completed_at__isnull=True,
            reserved_until__gt=now,
        )
        .order_by("reserved_until", "id")
    )


def reserve_medicine(medicine_id, user, now=None):
    """Reserve an available marketplace medicine for 24 hours and generate its pickup OTP."""
    now = now or timezone.now()
    release_expired_reservations(now)

    with transaction.atomic():
        medicine = Medicine.objects.select_for_update().get(id=medicine_id)

        if medicine.reserved_until and medicine.reserved_until <= now and medicine.completed_at is None:
            medicine.patient = None
            medicine.ordered_at = None
            medicine.reserved_until = None
            medicine.pickup_otp = ""
            medicine.otp_generated_at = None
            medicine.save(update_fields=["patient", "ordered_at", "reserved_until", "pickup_otp", "otp_generated_at"])

        if medicine.status != "verified" or not medicine.qr_code_id or medicine.completed_at is not None:
            return {"success": False, "medicine": medicine, "message": "This medicine is not available."}

        if medicine.patient_id:
            return {"success": False, "medicine": medicine, "message": "This medicine is currently reserved."}

        otp = generate_pickup_otp()
        medicine.patient = user
        medicine.ordered_at = now
        medicine.reserved_until = now + RESERVATION_DURATION
        medicine.pickup_otp = otp
        medicine.otp_generated_at = now
        medicine.save(update_fields=["patient", "ordered_at", "reserved_until", "pickup_otp", "otp_generated_at"])

    return {
        "success": True,
        "medicine": medicine,
        "otp": otp,
        "reserved_until": medicine.reserved_until,
    }


def verify_pickup_otp(identifier, otp, now=None):
    """Verify a pickup OTP by QR ID or medicine ID and mark the medicine as collected."""
    now = now or timezone.now()
    identifier = (identifier or "").strip()
    otp = (otp or "").strip()

    if not identifier or not otp:
        return {"success": False, "message": "Invalid OTP"}

    lookup = {"qr_code_id": identifier}
    if identifier.isdigit():
        lookup = {"id": int(identifier)}

    try:
        medicine = Medicine.objects.get(**lookup)
    except Medicine.DoesNotExist:
        return {"success": False, "message": "Invalid OTP"}

    if medicine.status == "sold" or medicine.completed_at:
        return {"success": False, "medicine": medicine, "message": "Invalid OTP"}

    if not medicine.patient_id or not medicine.reserved_until:
        return {"success": False, "medicine": medicine, "message": "Invalid OTP"}

    if medicine.reserved_until <= now:
        release_expired_reservations(now)
        return {"success": False, "medicine": medicine, "message": "Reservation expired."}

    if medicine.pickup_otp != otp:
        return {"success": False, "medicine": medicine, "message": "Invalid OTP"}

    medicine.status = "sold"
    medicine.completed_at = now
    medicine.reserved_until = None
    medicine.pickup_otp = ""
    medicine.otp_generated_at = None
    medicine.save(update_fields=["status", "completed_at", "reserved_until", "pickup_otp", "otp_generated_at"])

    return {"success": True, "medicine": medicine, "message": "Medicine collected successfully."}
