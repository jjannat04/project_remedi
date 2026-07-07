"""Impact dashboard statistics computed from medicine records."""

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from myapp.models import Medicine
from myapp.services.reservations import release_expired_reservations


def get_dashboard_statistics():
    """Return platform impact statistics calculated from the database."""
    now = timezone.now()
    release_expired_reservations(now)

    counts = Medicine.objects.aggregate(
        medicines_donated=Count("id"),
        medicines_approved=Count("id", filter=Q(status__in=["verified", "sold"])),
        medicines_rejected=Count("id", filter=Q(status="rejected")),
        medicines_reserved=Count(
            "id",
            filter=Q(
                status="verified",
                patient__isnull=False,
                completed_at__isnull=True,
                reserved_until__gt=now,
            ),
        ),
        medicines_collected=Count("id", filter=Q(status="sold", completed_at__isnull=False)),
        active_marketplace_listings=Count(
            "id",
            filter=Q(status="verified", patient__isnull=True, qr_code_id__isnull=False) & ~Q(qr_code_id=""),
        ),
    )
    counts["estimated_waste_prevented"] = counts["medicines_approved"]
    counts["estimated_patients_helped"] = counts["medicines_collected"]
    counts["has_data"] = counts["medicines_donated"] > 0
    return counts


def _has_chart_data(data):
    return any(value > 0 for value in data)


def get_dashboard_charts():
    """Return Chart.js-ready analytics calculated from medicine records."""
    now = timezone.now()
    release_expired_reservations(now)

    verification_counts = Medicine.objects.aggregate(
        approved=Count("id", filter=Q(status__in=["verified", "sold"])),
        rejected=Count("id", filter=Q(status="rejected")),
        pending=Count("id", filter=Q(status="pending")),
    )
    marketplace_counts = Medicine.objects.aggregate(
        available=Count(
            "id",
            filter=Q(status="verified", patient__isnull=True, qr_code_id__isnull=False) & ~Q(qr_code_id=""),
        ),
        reserved=Count(
            "id",
            filter=Q(
                status="verified",
                patient__isnull=False,
                completed_at__isnull=True,
                reserved_until__gt=now,
            ),
        ),
        collected=Count("id", filter=Q(status="sold", completed_at__isnull=False)),
    )
    risk_counts = Medicine.objects.aggregate(
        low=Count(
            "id",
            filter=Q(is_physical_intact=True, is_authentic=True, is_expiry_valid=True),
        ),
        medium=Count(
            "id",
            filter=(
                Q(is_physical_intact=True, is_authentic=True, is_expiry_valid=False)
                | Q(is_physical_intact=True, is_authentic=False, is_expiry_valid=True)
                | Q(is_physical_intact=False, is_authentic=True, is_expiry_valid=True)
            ),
        ),
        high=Count(
            "id",
            filter=Q(is_physical_intact=False) & Q(is_authentic=False)
            | Q(is_physical_intact=False) & Q(is_expiry_valid=False)
            | Q(is_authentic=False) & Q(is_expiry_valid=False),
        ),
    )
    medicine_rows = (
        Medicine.objects.values("name")
        .annotate(total=Count("id"))
        .order_by("-total", "name")[:5]
    )
    timeline_rows = (
        Medicine.objects.filter(status__in=["verified", "sold"], verified_at__isnull=False)
        .annotate(approved_date=TruncDate("verified_at"))
        .values("approved_date")
        .annotate(total=Count("id"))
        .order_by("approved_date")
    )

    charts = []

    verification_data = [
        verification_counts["approved"],
        verification_counts["rejected"],
        verification_counts["pending"],
    ]
    if _has_chart_data(verification_data):
        charts.append({
            "id": "verificationOutcomesChart",
            "title": "Verification Outcomes",
            "type": "pie",
            "labels": ["Approved", "Rejected", "Pending"],
            "data": verification_data,
            "backgroundColor": ["#059669", "#dc2626", "#f59e0b"],
        })

    marketplace_data = [
        marketplace_counts["available"],
        marketplace_counts["reserved"],
        marketplace_counts["collected"],
    ]
    if _has_chart_data(marketplace_data):
        charts.append({
            "id": "marketplaceDistributionChart",
            "title": "Marketplace Distribution",
            "type": "bar",
            "labels": ["Available", "Reserved", "Collected"],
            "data": marketplace_data,
            "backgroundColor": ["#10b981", "#0ea5e9", "#475569"],
        })

    risk_data = [risk_counts["low"], risk_counts["medium"], risk_counts["high"]]
    if _has_chart_data(risk_data):
        charts.append({
            "id": "riskLevelDistributionChart",
            "title": "Risk Level Distribution",
            "type": "bar",
            "labels": ["Low", "Medium", "High"],
            "data": risk_data,
            "backgroundColor": ["#22c55e", "#f59e0b", "#ef4444"],
        })

    medicine_labels = [row["name"] for row in medicine_rows]
    medicine_data = [row["total"] for row in medicine_rows]
    if _has_chart_data(medicine_data):
        charts.append({
            "id": "medicineCategoriesChart",
            "title": "Medicine Categories",
            "type": "bar",
            "labels": medicine_labels,
            "data": medicine_data,
            "backgroundColor": "#14b8a6",
            "indexAxis": "y",
        })

    timeline_labels = [row["approved_date"].isoformat() for row in timeline_rows]
    timeline_data = [row["total"] for row in timeline_rows]
    if _has_chart_data(timeline_data):
        charts.append({
            "id": "approvalTimelineChart",
            "title": "Timeline",
            "type": "line",
            "labels": timeline_labels,
            "data": timeline_data,
            "borderColor": "#2563eb",
            "backgroundColor": "rgba(37, 99, 235, 0.12)",
            "fill": True,
        })

    return {
        "has_data": bool(charts),
        "charts": charts,
    }
