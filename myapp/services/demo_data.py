"""Deterministic demo account and medicine helpers for judge-ready seeded data."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from myapp.models import Medicine, User
from myapp.services.analytics import calculate_demo_analytics


DEMO_PASSWORD = "ReMedi-Demo-2026-Internal"
DEMO_DONOR_EMAIL = "demo_donor@remedi.local"
DEMO_PHARMACIST_EMAIL = "demo_pharmacist@remedi.local"
DEMO_PATIENT_EMAIL = "demo_patient@remedi.local"
DEMO_BATCH_PREFIX = "RMD-DEMO-"


@dataclass(frozen=True)
class DemoUserSpec:
    key: str
    username: str
    email: str
    role: str
    first_name: str
    last_name: str
    license_number: str = ""
    phone: str = ""


DEMO_USER_SPECS = {
    "donor": DemoUserSpec(
        key="donor",
        username="demo_donor",
        email=DEMO_DONOR_EMAIL,
        role=User.Role.DONOR,
        first_name="Demo",
        last_name="Donor",
        phone="+8801000000001",
    ),
    "pharmacist": DemoUserSpec(
        key="pharmacist",
        username="demo_pharmacist",
        email=DEMO_PHARMACIST_EMAIL,
        role=User.Role.PHARMACIST,
        first_name="Demo",
        last_name="Pharmacist",
        license_number="DEMO-CENTRAL-PHARMACIST",
        phone="+8801000000002",
    ),
    "patient": DemoUserSpec(
        key="patient",
        username="demo_patient",
        email=DEMO_PATIENT_EMAIL,
        role=User.Role.PATIENT,
        first_name="Demo",
        last_name="Patient",
        phone="+8801000000003",
    ),
}


@dataclass(frozen=True)
class DemoMedicineSpec:
    key: str
    name: str
    scientific_name: str
    category: str
    batch_number: str
    expiry_date: date
    original_price: Decimal
    status: str
    qr_id: UUID
    is_physical_intact: bool = True
    is_authentic: bool = True
    is_expiry_valid: bool = True
    rejection_reason: str = ""
    patient_kind: str = ""
    ordered_at: datetime | None = None
    verified_at: datetime | None = None
    rejected_at: datetime | None = None
    completed_at: datetime | None = None


def _aware(year, month, day, hour=10, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute), timezone.get_current_timezone())


DEMO_MEDICINE_SPECS = (
    DemoMedicineSpec(
        key="pending",
        name="Napa 500 mg Tablet",
        scientific_name="Paracetamol",
        category="Pain relief",
        batch_number=f"{DEMO_BATCH_PREFIX}PENDING-001",
        expiry_date=date(2027, 8, 31),
        original_price=Decimal("180.00"),
        status="pending",
        qr_id=UUID("11111111-1111-4111-8111-111111111111"),
        is_physical_intact=False,
        is_authentic=False,
        is_expiry_valid=True,
    ),
    DemoMedicineSpec(
        key="verified_antibiotic",
        name="Cef-3 200 mg Capsule",
        scientific_name="Cefixime",
        category="Antibiotic",
        batch_number=f"{DEMO_BATCH_PREFIX}VERIFIED-001",
        expiry_date=date(2028, 1, 15),
        original_price=Decimal("720.00"),
        status="verified",
        qr_id=UUID("22222222-2222-4222-8222-222222222222"),
        verified_at=_aware(2026, 6, 14, 11, 30),
    ),
    DemoMedicineSpec(
        key="verified_diabetes",
        name="DP-Met 500 mg Tablet",
        scientific_name="Metformin Hydrochloride",
        category="Diabetes care",
        batch_number=f"{DEMO_BATCH_PREFIX}VERIFIED-002",
        expiry_date=date(2027, 11, 20),
        original_price=Decimal("540.00"),
        status="verified",
        qr_id=UUID("33333333-3333-4333-8333-333333333333"),
        verified_at=_aware(2026, 6, 16, 15, 45),
    ),
    DemoMedicineSpec(
        key="verified_respiratory",
        name="Montene 10 mg Tablet",
        scientific_name="Montelukast",
        category="Respiratory",
        batch_number=f"{DEMO_BATCH_PREFIX}VERIFIED-003",
        expiry_date=date(2028, 4, 10),
        original_price=Decimal("390.00"),
        status="verified",
        qr_id=UUID("44444444-4444-4444-8444-444444444444"),
        verified_at=_aware(2026, 6, 18, 9, 20),
    ),
    DemoMedicineSpec(
        key="rejected",
        name="Losectil 20 mg Capsule",
        scientific_name="Omeprazole",
        category="Digestive health",
        batch_number=f"{DEMO_BATCH_PREFIX}REJECTED-001",
        expiry_date=date(2026, 9, 5),
        original_price=Decimal("260.00"),
        status="rejected",
        qr_id=UUID("55555555-5555-4555-8555-555555555555"),
        is_physical_intact=False,
        is_authentic=True,
        is_expiry_valid=True,
        rejection_reason="Outer strip seal is damaged, so it cannot be redistributed safely.",
        rejected_at=_aware(2026, 6, 17, 14, 10),
    ),
    DemoMedicineSpec(
        key="reserved",
        name="Amdocal 5 mg Tablet",
        scientific_name="Amlodipine",
        category="Heart health",
        batch_number=f"{DEMO_BATCH_PREFIX}RESERVED-001",
        expiry_date=date(2027, 12, 1),
        original_price=Decimal("330.00"),
        status="verified",
        qr_id=UUID("66666666-6666-4666-8666-666666666666"),
        patient_kind="patient",
        ordered_at=_aware(2026, 6, 21, 13, 0),
        verified_at=_aware(2026, 6, 19, 16, 5),
    ),
    DemoMedicineSpec(
        key="sold",
        name="DP-Rab 20 mg Tablet",
        scientific_name="Rabeprazole Sodium",
        category="Digestive health",
        batch_number=f"{DEMO_BATCH_PREFIX}SOLD-001",
        expiry_date=date(2027, 10, 12),
        original_price=Decimal("460.00"),
        status="sold",
        qr_id=UUID("77777777-7777-4777-8777-777777777777"),
        patient_kind="patient",
        ordered_at=_aware(2026, 6, 11, 12, 15),
        verified_at=_aware(2026, 6, 8, 10, 40),
        completed_at=_aware(2026, 6, 12, 17, 30),
    ),
)


def _find_existing_user(spec):
    return User.objects.filter(Q(email=spec.email) | Q(username=spec.username)).first()


@transaction.atomic
def ensure_demo_user(kind):
    """Create or update one deterministic demo user and return (user, created)."""
    spec = DEMO_USER_SPECS[kind]
    user = _find_existing_user(spec)
    created = user is None

    if created:
        user = User(username=spec.username, email=spec.email)

    user.username = spec.username
    user.email = spec.email
    user.role = spec.role
    user.first_name = spec.first_name
    user.last_name = spec.last_name
    user.license_number = spec.license_number
    user.phone = spec.phone
    user.is_demo_account = True
    user.is_active = True
    user.set_password(DEMO_PASSWORD)
    user.save()

    return user, created


def ensure_demo_users():
    """Create or update all deterministic demo users."""
    results = {}
    for kind in DEMO_USER_SPECS:
        results[kind] = ensure_demo_user(kind)
    return results


def _medicine_defaults(spec, users):
    patient = users[spec.patient_kind][0] if spec.patient_kind else None
    return {
        "donor": users["donor"][0],
        "name": spec.name,
        "scientific_name": spec.scientific_name,
        "category": spec.category,
        "expiry_date": spec.expiry_date,
        "original_price": spec.original_price,
        "status": spec.status,
        "qr_id": spec.qr_id,
        "is_physical_intact": spec.is_physical_intact,
        "is_authentic": spec.is_authentic,
        "is_expiry_valid": spec.is_expiry_valid,
        "rejection_reason": spec.rejection_reason,
        "patient": patient,
        "ordered_at": spec.ordered_at,
        "verified_at": spec.verified_at,
        "rejected_at": spec.rejected_at,
        "completed_at": spec.completed_at,
    }


@transaction.atomic
def ensure_demo_medicines(users=None):
    """Create or refresh deterministic demo medicines and return (medicine, created)."""
    users = users or ensure_demo_users()
    results = {}

    for spec in DEMO_MEDICINE_SPECS:
        matches = list(Medicine.objects.filter(batch_number=spec.batch_number).order_by("id"))
        medicine = matches[0] if matches else Medicine(batch_number=spec.batch_number)
        created = not matches

        for field, value in _medicine_defaults(spec, users).items():
            setattr(medicine, field, value)
        medicine.save()

        duplicate_ids = [duplicate.id for duplicate in matches[1:]]
        if duplicate_ids:
            Medicine.objects.filter(id__in=duplicate_ids).delete()

        results[spec.key] = (medicine, created)

    return results


def seed_demo_dataset():
    """Create or refresh all deterministic demo accounts and medicines."""
    users = ensure_demo_users()
    medicines = ensure_demo_medicines(users)
    analytics = calculate_demo_analytics()
    return {
        "users": users,
        "medicines": medicines,
        "analytics": analytics,
    }


def is_seeded_demo_data_ready():
    return Medicine.objects.filter(batch_number__startswith=DEMO_BATCH_PREFIX).exists()
