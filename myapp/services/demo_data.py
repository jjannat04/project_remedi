"""Deterministic demo account helpers for judge-ready seeded data."""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q

from myapp.models import User


DEMO_PASSWORD = "ReMedi-Demo-2026-Internal"
DEMO_DONOR_EMAIL = "demo_donor@remedi.local"
DEMO_PHARMACIST_EMAIL = "demo_pharmacist@remedi.local"


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
}

DEMO_PLACEHOLDERS = (
    "Demo account shell for donor workflows",
    "Demo account shell for central pharmacist workflows",
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


def get_demo_placeholders():
    """Return placeholder labels for future seeded demo data without creating medicines."""
    return DEMO_PLACEHOLDERS
