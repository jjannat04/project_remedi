"""Reusable analytics helpers for donation and demo dashboards."""

from decimal import Decimal

from django.db.models import Q

from myapp.models import Medicine


def demo_medicine_queryset():
    return Medicine.objects.filter(Q(donor__is_demo_account=True) | Q(patient__is_demo_account=True)).distinct()


def calculate_medicine_analytics(medicines=None):
    medicines = medicines if medicines is not None else Medicine.objects.all()
    rows = list(medicines)
    sold_rows = [medicine for medicine in rows if medicine.status == "sold"]
    verified_rows = [medicine for medicine in rows if medicine.status in {"verified", "sold"}]
    rejected_rows = [medicine for medicine in rows if medicine.status == "rejected"]
    patient_ids = {medicine.patient_id for medicine in rows if medicine.patient_id}

    estimated_savings = sum(
        (medicine.original_price or Decimal("0")) - (medicine.resale_price or Decimal("0"))
        for medicine in sold_rows
    )

    return {
        "medicines_donated": len(rows),
        "medicines_verified": len(verified_rows),
        "medicines_rejected": len(rejected_rows),
        "medicines_redistributed": len(sold_rows),
        "estimated_savings": estimated_savings,
        "waste_prevented_count": len(verified_rows),
        "patients_helped_count": len(patient_ids),
    }


def calculate_demo_analytics():
    return calculate_medicine_analytics(demo_medicine_queryset())
