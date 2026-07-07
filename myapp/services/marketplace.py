"""Marketplace query helpers for public medicine listings."""

from django.db.models import Q

from myapp.models import Medicine


def get_marketplace_medicines(search_query=""):
    """Return public marketplace medicines approved by pharmacists and QR verified."""
    medicines = (
        Medicine.objects
        .filter(status="verified", patient__isnull=True, qr_code_id__isnull=False)
        .exclude(qr_code_id="")
        .order_by("-verified_at", "-id")
        .distinct()
    )
    search_query = (search_query or "").strip()
    if search_query:
        medicines = medicines.filter(
            Q(name__icontains=search_query)
            | Q(scientific_name__icontains=search_query)
        )
    return medicines


def get_marketplace_medicine(medicine_id):
    """Return one public marketplace medicine by ID."""
    return get_marketplace_medicines().get(id=medicine_id)
