"""Deterministic, anonymized impact reports from aggregate platform data."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from myapp.models import Medicine
from myapp.services.dashboard import get_dashboard_statistics


REPORT_TYPES = {
    "overall": "Overall Impact Summary",
    "weekly": "Weekly Impact Summary",
    "waste": "Medicine Waste Prevention Summary",
    "affordability": "Affordability Impact Summary",
    "csr": "CSR / ESG Summary",
}


def _percent(numerator, denominator):
    if not denominator:
        return Decimal("0.00")
    return (Decimal(numerator) / Decimal(denominator) * Decimal("100")).quantize(Decimal("0.01"))


def _money(value):
    return f"{Decimal(value or 0).quantize(Decimal('0.01'))} BDT"


def _base_metrics():
    statistics = get_dashboard_statistics()
    donated = statistics["medicines_donated"]
    approved = statistics["medicines_approved"]
    collected = statistics["medicines_collected"]
    sold_totals = Medicine.objects.filter(status="sold", completed_at__isnull=False).aggregate(
        original_total=Sum("original_price"),
        resale_total=Sum("resale_price"),
    )
    total_savings = (sold_totals["original_total"] or Decimal("0")) - (sold_totals["resale_total"] or Decimal("0"))

    return {
        **statistics,
        "approval_rate": _percent(approved, donated),
        "collection_rate": _percent(collected, approved),
        "total_savings": total_savings,
    }


def _report(title, report_type, lines, has_data):
    return {
        "type": report_type,
        "title": title,
        "content": "\n".join(lines) if has_data else "",
        "has_data": has_data,
        "filename": f"remedi-{report_type}-impact-report.txt",
    }


def generate_overall_report():
    metrics = _base_metrics()
    has_data = metrics["has_data"]
    lines = [
        f"ReMedi has processed {metrics['medicines_donated']} donated medicines.",
        f"{metrics['medicines_approved']} medicines were approved and {metrics['medicines_rejected']} were rejected.",
        f"{metrics['active_marketplace_listings']} medicines are currently available in the marketplace.",
        f"{metrics['medicines_reserved']} medicines are reserved and {metrics['medicines_collected']} medicines have reached patients.",
        f"The approval rate is {metrics['approval_rate']}% and the collection rate is {metrics['collection_rate']}%.",
        f"The platform has prevented an estimated {metrics['estimated_waste_prevented']} medicines from becoming waste while helping an estimated {metrics['estimated_patients_helped']} patients.",
    ]
    return _report(REPORT_TYPES["overall"], "overall", lines, has_data)


def generate_weekly_report():
    start = timezone.now() - timedelta(days=7)
    approved = Medicine.objects.filter(status__in=["verified", "sold"], verified_at__gte=start).count()
    rejected = Medicine.objects.filter(status="rejected", rejected_at__gte=start).count()
    collected = Medicine.objects.filter(status="sold", completed_at__gte=start).count()
    has_data = any([approved, rejected, collected])
    approval_rate = _percent(approved, approved + rejected)
    lines = [
        "This weekly ReMedi impact summary covers verified platform activity from the last 7 days.",
        f"{approved} medicines were approved during this period.",
        f"{rejected} medicines were rejected during this period.",
        f"{collected} medicines were collected by patients during this period.",
        f"The weekly approval rate is {approval_rate}%.",
        "These aggregate results show short-term progress without exposing donor or patient identities.",
    ]
    return _report(REPORT_TYPES["weekly"], "weekly", lines, has_data)


def generate_waste_report():
    metrics = _base_metrics()
    has_data = metrics["has_data"]
    lines = [
        f"ReMedi has reviewed {metrics['medicines_donated']} donated medicines for reuse potential.",
        f"{metrics['medicines_approved']} medicines were approved for redistribution.",
        f"{metrics['medicines_rejected']} medicines were rejected to protect patient safety.",
        f"The estimated medicine waste prevented count is {metrics['estimated_waste_prevented']}.",
        f"{metrics['active_marketplace_listings']} approved medicines remain available for patient access.",
        "The platform reduces avoidable medicine waste by moving safe, approved medicines back into use.",
    ]
    return _report(REPORT_TYPES["waste"], "waste", lines, has_data)


def generate_affordability_report():
    metrics = _base_metrics()
    has_data = metrics["has_data"]
    lines = [
        f"ReMedi has helped an estimated {metrics['estimated_patients_helped']} patients access collected medicines.",
        f"{metrics['medicines_collected']} medicines have been collected through the platform.",
        f"{metrics['medicines_reserved']} medicines are currently reserved for patients.",
        f"The estimated affordability benefit from collected medicines is {_money(metrics['total_savings'])}.",
        f"The collection rate is {metrics['collection_rate']}% of approved medicines.",
        "The platform improves affordability by offering approved medicines at a reduced resale price.",
    ]
    return _report(REPORT_TYPES["affordability"], "affordability", lines, has_data)


def generate_csr_report():
    metrics = _base_metrics()
    has_data = metrics["has_data"]
    lines = [
        "ReMedi supports circular healthcare goals through verified medicine redistribution.",
        f"The platform has processed {metrics['medicines_donated']} donated medicines.",
        f"{metrics['estimated_waste_prevented']} medicines are estimated to have been prevented from becoming waste.",
        f"{metrics['estimated_patients_helped']} patients are estimated to have been helped through collected medicines.",
        f"The approval rate is {metrics['approval_rate']}% and the collection rate is {metrics['collection_rate']}%.",
        "These aggregate indicators can support NGO, hospital, pharmacy partner, CSR, and ESG reporting.",
    ]
    return _report(REPORT_TYPES["csr"], "csr", lines, has_data)


REPORT_GENERATORS = {
    "overall": generate_overall_report,
    "weekly": generate_weekly_report,
    "waste": generate_waste_report,
    "affordability": generate_affordability_report,
    "csr": generate_csr_report,
}


def generate_report(report_type):
    return REPORT_GENERATORS.get(report_type, generate_overall_report)()
