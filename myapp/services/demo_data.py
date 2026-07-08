"""Deterministic demo account and medicine helpers for judge-ready seeded data."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from myapp.models import Medicine, ReMediCorner, User
from myapp.services.analytics import calculate_demo_analytics
from myapp.services.qr import ensure_medicine_qr


DEMO_PASSWORD = "remedi4567"
DEMO_DONOR_EMAIL = "demo_donor@remedi.local"
DEMO_PHARMACIST_EMAIL = "demo_pharmacist@remedi.local"
DEMO_PATIENT_EMAIL = "demo_patient@remedi.local"
DEMO_BATCH_PREFIX = "RMD-DEMO-"
DEMO_CORNER_PREFIX = "ReMedi Demo Corner"


@dataclass(frozen=True)
class DemoUserSpec:
    key: str
    username: str
    email: str
    role: str
    first_name: str
    last_name: str
    phone: str
    nid: str
    license_number: str = ""


DEMO_USER_SPECS = (
    DemoUserSpec("donor", "demo_donor", DEMO_DONOR_EMAIL, User.Role.DONOR, "Nusrat", "Jahan", "01710000001", "1990010100001"),
    DemoUserSpec("patient", "demo_patient", DEMO_PATIENT_EMAIL, User.Role.PATIENT, "Arif", "Rahman", "01710000002", "1992020200002"),
    DemoUserSpec("user_03", "sadia_akter", "sadia.akter@remedi.local", User.Role.DONOR, "Sadia", "Akter", "01710000003", "1993030300003"),
    DemoUserSpec("user_04", "tanvir_hasan", "tanvir.hasan@remedi.local", User.Role.DONOR, "Tanvir", "Hasan", "01710000004", "1994040400004"),
    DemoUserSpec("user_05", "mahin_islam", "mahin.islam@remedi.local", User.Role.DONOR, "Mahin", "Islam", "01710000005", "1995050500005"),
    DemoUserSpec("user_06", "farzana_rahman", "farzana.rahman@remedi.local", User.Role.DONOR, "Farzana", "Rahman", "01710000006", "1996060600006"),
    DemoUserSpec("user_07", "riyad_khan", "riyad.khan@remedi.local", User.Role.PATIENT, "Riyad", "Khan", "01710000007", "1997070700007"),
    DemoUserSpec("user_08", "lamia_chowdhury", "lamia.chowdhury@remedi.local", User.Role.PATIENT, "Lamia", "Chowdhury", "01710000008", "1998080800008"),
    DemoUserSpec("user_09", "saif_mahmud", "saif.mahmud@remedi.local", User.Role.DONOR, "Saif", "Mahmud", "01710000009", "1999090900009"),
    DemoUserSpec("user_10", "nabila_karim", "nabila.karim@remedi.local", User.Role.PATIENT, "Nabila", "Karim", "01710000010", "2000101000010"),
    DemoUserSpec("pharmacist", "demo_pharmacist", DEMO_PHARMACIST_EMAIL, User.Role.PHARMACIST, "Dr. Farhan", "Kabir", "01710000011", "1985111100011", "BPC-DEMO-1001"),
    DemoUserSpec("pharmacist_02", "dr_samira_haque", "samira.haque@remedi.local", User.Role.PHARMACIST, "Dr. Samira", "Haque", "01710000012", "1986121200012", "BPC-DEMO-1002"),
    DemoUserSpec("pharmacist_03", "dr_ashik_sen", "ashik.sen@remedi.local", User.Role.PHARMACIST, "Dr. Ashik", "Sen", "01710000013", "1987131300013", "BPC-DEMO-1003"),
)


@dataclass(frozen=True)
class DemoCornerSpec:
    name: str
    address: str
    city: str
    latitude: float
    longitude: float


DEMO_CORNER_SPECS = (
    DemoCornerSpec(f"{DEMO_CORNER_PREFIX} - Dhanmondi", "House 42, Road 7A, Dhanmondi", "Dhaka", 23.7465, 90.3760),
    DemoCornerSpec(f"{DEMO_CORNER_PREFIX} - Uttara", "Sector 7, Rabindra Sarani, Uttara", "Dhaka", 23.8759, 90.3795),
    DemoCornerSpec(f"{DEMO_CORNER_PREFIX} - Agrabad", "Sheikh Mujib Road, Agrabad", "Chattogram", 22.3245, 91.8123),
    DemoCornerSpec(f"{DEMO_CORNER_PREFIX} - Feni", "S S K Road, Feni Sadar", "Feni", 23.0159, 91.3976),
    DemoCornerSpec(f"{DEMO_CORNER_PREFIX} - Sylhet", "Zindabazar, Sylhet", "Sylhet", 24.8949, 91.8687),
)


@dataclass(frozen=True)
class DemoMedicineSpec:
    key: str
    donor_key: str
    patient_key: str
    reviewer_key: str
    name: str
    scientific_name: str
    dosage: str
    manufacturer: str
    category: str
    batch_number: str
    expiry_date: date
    original_price: Decimal
    status: str
    quantity: int
    package_type: str
    opened: bool
    storage_condition: str
    risk_level: str
    decision: str
    offset_days: int
    is_physical_intact: bool = True
    is_authentic: bool = True
    is_expiry_valid: bool = True
    rejection_reason: str = ""
    reservation_state: str = ""


MEDICINE_ROWS = (
    ("pending_napa", "donor", "", "", "Napa 500 mg Tablet", "Paracetamol", "500 mg", "Beximco Pharmaceuticals", "Painkiller", "PEN-001", date(2027, 8, 31), "180.00", "pending", 2, "strip", False, "cool_dry", "Medium", "review", 150, False, True, True, "", ""),
    ("verified_cef3", "user_03", "", "pharmacist", "Cef-3 200 mg Capsule", "Cefixime", "200 mg", "Square Pharmaceuticals", "Antibiotic", "APP-001", date(2028, 1, 15), "720.00", "verified", 1, "box", False, "room_temperature", "Low", "accept", 145, True, True, True, "", ""),
    ("verified_dpmet", "user_04", "", "pharmacist_02", "DP-Met 500 mg Tablet", "Metformin Hydrochloride", "500 mg", "Drug International", "Diabetes", "APP-002", date(2027, 11, 20), "540.00", "verified", 3, "strip", False, "cool_dry", "Low", "accept", 140, True, True, True, "", ""),
    ("verified_montene", "user_05", "", "pharmacist_03", "Montene 10 mg Tablet", "Montelukast", "10 mg", "Aristopharma", "Respiratory", "APP-003", date(2028, 4, 10), "390.00", "verified", 1, "strip", False, "cool_dry", "Low", "accept", 136, True, True, True, "", ""),
    ("rejected_losectil", "donor", "", "pharmacist", "Losectil 20 mg Capsule", "Omeprazole", "20 mg", "Eskayef", "Digestive health", "REJ-001", date(2026, 9, 5), "260.00", "rejected", 1, "strip", True, "unknown", "High", "reject", 132, False, True, True, "Outer strip seal is damaged, so it cannot be redistributed safely.", ""),
    ("reserved_amdocal", "user_09", "patient", "pharmacist_02", "Amdocal 5 mg Tablet", "Amlodipine", "5 mg", "Beximco Pharmaceuticals", "Hypertension", "RSV-001", date(2027, 12, 1), "330.00", "verified", 2, "strip", False, "room_temperature", "Low", "accept", 127, True, True, True, "", "reserved"),
    ("sold_dprab", "donor", "patient", "pharmacist_03", "DP-Rab 20 mg Tablet", "Rabeprazole Sodium", "20 mg", "Drug International", "Digestive health", "SLD-001", date(2027, 10, 12), "460.00", "sold", 1, "strip", False, "cool_dry", "Low", "accept", 122, True, True, True, "", "collected"),
    ("verified_seclo", "user_03", "", "pharmacist", "Seclo 20 mg Capsule", "Omeprazole", "20 mg", "Square Pharmaceuticals", "Digestive health", "APP-004", date(2028, 2, 20), "300.00", "verified", 4, "box", False, "cool_dry", "Low", "accept", 116, True, True, True, "", ""),
    ("verified_maxpro", "user_04", "", "pharmacist_02", "Maxpro 20 mg Tablet", "Esomeprazole", "20 mg", "Renata Limited", "Digestive health", "APP-005", date(2027, 9, 18), "360.00", "verified", 2, "strip", False, "room_temperature", "Low", "accept", 111, True, True, True, "", ""),
    ("verified_bisocor", "user_05", "", "pharmacist_03", "Bisocor 2.5 Tablet", "Bisoprolol", "2.5 mg", "Incepta Pharmaceuticals", "Hypertension", "APP-006", date(2028, 5, 11), "410.00", "verified", 1, "strip", False, "cool_dry", "Low", "accept", 106, True, True, True, "", ""),
    ("verified_comet", "user_06", "", "pharmacist", "Comet 500 Tablet", "Metformin", "500 mg", "ACI Limited", "Diabetes", "APP-007", date(2027, 7, 30), "250.00", "verified", 3, "strip", False, "room_temperature", "Low", "accept", 101, True, True, True, "", ""),
    ("reserved_salmolin", "user_09", "user_07", "pharmacist_02", "Salmolin Inhaler", "Salbutamol", "100 mcg", "Acme Laboratories", "Respiratory", "RSV-002", date(2027, 6, 30), "420.00", "verified", 1, "injection", False, "room_temperature", "Low", "accept", 96, True, True, True, "", "reserved"),
    ("sold_calbo", "donor", "user_08", "pharmacist_03", "Calbo-D Tablet", "Calcium + Vitamin D3", "500 mg", "Square Pharmaceuticals", "Vitamins", "SLD-002", date(2028, 3, 15), "280.00", "sold", 2, "box", False, "cool_dry", "Low", "accept", 91, True, True, True, "", "collected"),
    ("sold_fexo", "user_03", "user_10", "pharmacist", "Fexo 120 Tablet", "Fexofenadine", "120 mg", "Beximco Pharmaceuticals", "Respiratory", "SLD-003", date(2027, 8, 7), "350.00", "sold", 1, "strip", False, "room_temperature", "Low", "accept", 86, True, True, True, "", "collected"),
    ("pending_zimax", "user_04", "", "", "Zimax 500 Tablet", "Azithromycin", "500 mg", "Square Pharmaceuticals", "Antibiotic", "PEN-002", date(2027, 3, 22), "850.00", "pending", 1, "strip", False, "unknown", "Medium", "review", 82, True, True, False, "", ""),
    ("pending_orsaline", "user_05", "", "", "ORS Saline-N", "Oral Rehydration Salts", "10.25 g", "Social Marketing Company", "Children", "PEN-003", date(2027, 2, 12), "120.00", "pending", 6, "box", False, "cool_dry", "Low", "review", 78, True, False, True, "", ""),
    ("rejected_expired", "user_06", "", "pharmacist_02", "Expired Napa Syrup", "Paracetamol", "120 mg/5 ml", "Beximco Pharmaceuticals", "Children", "REJ-002", date(2025, 11, 20), "190.00", "rejected", 1, "bottle", True, "unknown", "High", "reject", 74, True, True, False, "Expiry date is already past and bottle was opened.", ""),
    ("rejected_water", "user_09", "", "pharmacist_03", "DP-Clox Capsule", "Cloxacillin", "500 mg", "Drug International", "Antibiotic", "REJ-003", date(2027, 1, 5), "620.00", "rejected", 1, "box", True, "unknown", "High", "reject", 70, False, True, True, "Water damage marks visible on the carton.", ""),
    ("rejected_blurry", "donor", "", "pharmacist", "Unclear Insulin Pen", "Insulin Glargine", "100 IU/ml", "Unknown", "Diabetes", "REJ-004", date(2027, 12, 24), "1200.00", "rejected", 1, "injection", False, "refrigerated", "High", "reject", 66, False, False, True, "Label and batch number are unreadable, requiring rejection.", ""),
    ("verified_cevit", "user_03", "", "pharmacist_02", "Ceevit Tablet", "Vitamin C", "250 mg", "Square Pharmaceuticals", "Vitamins", "APP-008", date(2028, 6, 19), "160.00", "verified", 5, "strip", False, "cool_dry", "Low", "accept", 62, True, True, True, "", ""),
    ("verified_napa_syrup", "user_04", "", "pharmacist_03", "Napa Syrup", "Paracetamol", "120 mg/5 ml", "Beximco Pharmaceuticals", "Children", "APP-009", date(2027, 10, 2), "150.00", "verified", 1, "bottle", False, "room_temperature", "Low", "accept", 58, True, True, True, "", ""),
    ("verified_tofen", "user_05", "", "pharmacist", "Tofen Syrup", "Ketotifen", "1 mg/5 ml", "Square Pharmaceuticals", "Children", "APP-010", date(2027, 5, 18), "210.00", "verified", 1, "bottle", False, "room_temperature", "Low", "accept", 54, True, True, True, "", ""),
    ("verified_cardobis", "user_06", "", "pharmacist_02", "Cardobis 5 Tablet", "Bisoprolol", "5 mg", "Incepta Pharmaceuticals", "Hypertension", "APP-011", date(2028, 1, 30), "430.00", "verified", 2, "strip", False, "cool_dry", "Low", "accept", 50, True, True, True, "", ""),
    ("reserved_expired", "user_09", "user_07", "pharmacist_03", "Old Reservation Vitamin B", "Vitamin B Complex", "50 mg", "Aristopharma", "Vitamins", "EXP-RSV-001", date(2027, 4, 14), "200.00", "verified", 1, "strip", False, "cool_dry", "Medium", "review", 46, True, True, True, "", "expired_reservation"),
    ("sold_az", "donor", "user_08", "pharmacist", "Azithrocin 500 Tablet", "Azithromycin", "500 mg", "Acme Laboratories", "Antibiotic", "SLD-004", date(2027, 9, 10), "790.00", "sold", 1, "strip", False, "cool_dry", "Low", "accept", 42, True, True, True, "", "collected"),
    ("verified_glucored", "user_03", "", "pharmacist_02", "Glucored 80 Tablet", "Gliclazide", "80 mg", "Eskayef", "Diabetes", "APP-012", date(2027, 11, 11), "370.00", "verified", 2, "strip", False, "cool_dry", "Low", "accept", 38, True, True, True, "", ""),
    ("verified_losardil", "user_04", "", "pharmacist_03", "Losardil 50 Tablet", "Losartan Potassium", "50 mg", "Square Pharmaceuticals", "Hypertension", "APP-013", date(2028, 2, 2), "400.00", "verified", 3, "strip", False, "room_temperature", "Low", "accept", 34, True, True, True, "", ""),
    ("verified_seretide", "user_05", "", "pharmacist", "DP-Vent Inhaler", "Salbutamol", "100 mcg", "Drug International", "Respiratory", "APP-014", date(2027, 8, 18), "510.00", "verified", 1, "injection", False, "room_temperature", "Low", "accept", 30, True, True, True, "", ""),
    ("near_expiry", "user_06", "", "pharmacist_02", "Near Expiry Zinc", "Zinc Sulfate", "20 mg", "Renata Limited", "Vitamins", "APP-015", date(2026, 8, 25), "180.00", "verified", 1, "strip", False, "cool_dry", "Medium", "review", 26, True, True, True, "", ""),
    ("pending_insulin", "user_09", "", "", "Insulet R Injection", "Regular Insulin", "100 IU/ml", "Incepta Pharmaceuticals", "Diabetes", "PEN-004", date(2027, 12, 30), "980.00", "pending", 1, "injection", False, "refrigerated", "Medium", "review", 22, True, True, False, "", ""),
    ("rejected_tamper", "donor", "", "pharmacist_03", "Tampered Cefixime Box", "Cefixime", "400 mg", "Unknown", "Antibiotic", "REJ-005", date(2028, 5, 7), "920.00", "rejected", 1, "box", True, "unknown", "High", "reject", 18, False, False, True, "Possible tampered seal and counterfeit warning signs.", ""),
    ("verified_multivit", "user_03", "", "pharmacist", "Multivit Plus Tablet", "Multivitamin", "Once daily", "Healthcare Pharma", "Vitamins", "APP-016", date(2028, 7, 7), "450.00", "verified", 4, "box", False, "cool_dry", "Low", "accept", 14, True, True, True, "", ""),
    ("verified_ace", "user_04", "", "pharmacist_02", "Ace 500 Tablet", "Paracetamol", "500 mg", "Square Pharmaceuticals", "Painkiller", "APP-017", date(2027, 9, 9), "170.00", "verified", 2, "strip", False, "room_temperature", "Low", "accept", 10, True, True, True, "", ""),
    ("verified_sitagil", "user_05", "", "pharmacist_03", "Sitagil M Tablet", "Sitagliptin + Metformin", "50/500 mg", "Incepta Pharmaceuticals", "Diabetes", "APP-018", date(2028, 3, 21), "690.00", "verified", 1, "strip", False, "cool_dry", "Low", "accept", 7, True, True, True, "", ""),
    ("pending_child_cold", "user_06", "", "", "Kids Cold Syrup", "Chlorpheniramine + Phenylephrine", "2 mg/5 ml", "Acme Laboratories", "Children", "PEN-005", date(2027, 1, 19), "240.00", "pending", 1, "bottle", False, "room_temperature", "Medium", "review", 4, False, True, True, "", ""),
    ("verified_inhaler", "user_09", "", "pharmacist", "Monas 10 Tablet", "Montelukast", "10 mg", "Acme Laboratories", "Respiratory", "APP-019", date(2028, 8, 12), "480.00", "verified", 2, "strip", False, "cool_dry", "Low", "accept", 1, True, True, True, "", ""),
)


DEMO_MEDICINE_SPECS = tuple(
    DemoMedicineSpec(
        key=row[0],
        donor_key=row[1],
        patient_key=row[2],
        reviewer_key=row[3],
        name=row[4],
        scientific_name=row[5],
        dosage=row[6],
        manufacturer=row[7],
        category=row[8],
        batch_number=f"{DEMO_BATCH_PREFIX}{row[9]}",
        expiry_date=row[10],
        original_price=Decimal(row[11]),
        status=row[12],
        quantity=row[13],
        package_type=row[14],
        opened=row[15],
        storage_condition=row[16],
        risk_level=row[17],
        decision=row[18],
        offset_days=row[19],
        is_physical_intact=row[20],
        is_authentic=row[21],
        is_expiry_valid=row[22],
        rejection_reason=row[23],
        reservation_state=row[24],
    )
    for row in MEDICINE_ROWS
)


def _aware_from_offset(offset_days, hour=10, minute=0):
    now = timezone.now()
    base = now - timedelta(days=offset_days)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _find_existing_user(spec):
    return User.objects.filter(Q(email=spec.email) | Q(username=spec.username), is_superuser=False).first()


def _safe_demo_username(spec):
    if not User.objects.filter(username=spec.username, is_superuser=True).exists():
        return spec.username
    return f"{spec.username}_demo"


@transaction.atomic
def ensure_demo_user(kind):
    """Create or update one deterministic demo user and return (user, created)."""
    spec = next(item for item in DEMO_USER_SPECS if item.key == kind)
    user = _find_existing_user(spec)
    created = user is None

    if created:
        user = User(username=_safe_demo_username(spec), email=spec.email)

    user.username = _safe_demo_username(spec)
    user.email = spec.email
    user.role = spec.role
    user.first_name = spec.first_name
    user.last_name = spec.last_name
    user.license_number = spec.license_number
    user.phone = spec.phone
    user.nid = spec.nid
    user.is_demo_account = True
    user.is_active = True
    user.set_password(DEMO_PASSWORD)
    user.save()

    return user, created


def ensure_demo_users():
    """Create or update all deterministic demo users."""
    return {spec.key: ensure_demo_user(spec.key) for spec in DEMO_USER_SPECS}


@transaction.atomic
def ensure_demo_corners():
    """Create or update deterministic demo pickup locations."""
    results = {}
    for spec in DEMO_CORNER_SPECS:
        corner, created = ReMediCorner.objects.update_or_create(
            name=spec.name,
            defaults={
                "address": spec.address,
                "city": spec.city,
                "latitude": spec.latitude,
                "longitude": spec.longitude,
            },
        )
        results[spec.name] = (corner, created)
    return results


def _pickup_fields(spec, patient):
    if not spec.reservation_state:
        return {
            "patient": None,
            "ordered_at": None,
            "reserved_until": None,
            "pickup_otp": "",
            "otp_generated_at": None,
            "completed_at": None,
        }

    ordered_at = _aware_from_offset(max(spec.offset_days - 1, 0), 11, 15)
    if spec.reservation_state == "reserved":
        return {
            "patient": patient,
            "ordered_at": ordered_at,
            "reserved_until": timezone.now() + timedelta(hours=20 + spec.offset_days % 4),
            "pickup_otp": f"{100000 + spec.offset_days:06d}"[-6:],
            "otp_generated_at": ordered_at,
            "completed_at": None,
        }
    if spec.reservation_state == "expired_reservation":
        return {
            "patient": patient,
            "ordered_at": ordered_at,
            "reserved_until": timezone.now() - timedelta(hours=6),
            "pickup_otp": f"{200000 + spec.offset_days:06d}"[-6:],
            "otp_generated_at": ordered_at,
            "completed_at": None,
        }
    return {
        "patient": patient,
        "ordered_at": ordered_at,
        "reserved_until": None,
        "pickup_otp": "",
        "otp_generated_at": None,
        "completed_at": _aware_from_offset(max(spec.offset_days - 2, 0), 16, 30),
    }


def _medicine_defaults(spec, users):
    donor = users[spec.donor_key][0]
    patient = users[spec.patient_key][0] if spec.patient_key else None
    submitted_at = _aware_from_offset(spec.offset_days, 9, 30)
    pickup = _pickup_fields(spec, patient)
    verified_at = None
    rejected_at = None
    if spec.status in {"verified", "sold"}:
        verified_at = submitted_at + timedelta(hours=6)
    if spec.status == "rejected":
        rejected_at = submitted_at + timedelta(hours=5)

    return {
        "donor": donor,
        "name": spec.name,
        "scientific_name": spec.scientific_name,
        "dosage": spec.dosage,
        "manufacturer": spec.manufacturer,
        "category": spec.category,
        "expiry_date": spec.expiry_date,
        "original_price": spec.original_price,
        "status": spec.status,
        "is_physical_intact": spec.is_physical_intact,
        "is_authentic": spec.is_authentic,
        "is_expiry_valid": spec.is_expiry_valid,
        "rejection_reason": spec.rejection_reason,
        "verified_at": verified_at,
        "rejected_at": rejected_at,
        "donor_phone": donor.phone,
        "donation_address": f"House {10 + spec.offset_days % 70}, Road {1 + spec.offset_days % 12}, {donor.last_name} Area",
        "district": "Dhaka" if spec.offset_days % 3 else "Chattogram",
        "area": ["Dhanmondi", "Uttara", "Agrabad", "Feni Sadar"][spec.offset_days % 4],
        "pickup_notes": f"Demo AI summary: {spec.decision.title()} recommendation, {spec.risk_level.lower()} visual risk.",
        "quantity": spec.quantity,
        "package_type": spec.package_type,
        "opened": spec.opened,
        "storage_condition": spec.storage_condition,
        **pickup,
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

        if medicine.status in {"verified", "sold"}:
            ensure_medicine_qr(medicine)
            medicine.refresh_from_db()

        results[spec.key] = (medicine, created)

    return results


def demo_summary():
    """Return counts used by management command output."""
    medicines = Medicine.objects.filter(batch_number__startswith=DEMO_BATCH_PREFIX)
    active_reservations = medicines.filter(
        status="verified",
        patient__isnull=False,
        completed_at__isnull=True,
        reserved_until__gt=timezone.now(),
    )
    return {
        "regular_users": User.objects.filter(is_demo_account=True).exclude(role=User.Role.PHARMACIST).count(),
        "pharmacists": User.objects.filter(is_demo_account=True, role=User.Role.PHARMACIST).count(),
        "medicines": medicines.count(),
        "marketplace_listings": medicines.filter(status="verified", patient__isnull=True, qr_code_id__isnull=False).exclude(qr_code_id="").count(),
        "reservations": medicines.filter(patient__isnull=False).count(),
        "active_reservations": active_reservations.count(),
        "qr_codes": medicines.filter(qr_code_id__isnull=False).exclude(qr_code_id="").count(),
        "corners": ReMediCorner.objects.filter(name__startswith=DEMO_CORNER_PREFIX).count(),
    }


def seed_demo_dataset():
    """Create or refresh all deterministic demo accounts, locations, and medicines."""
    users = ensure_demo_users()
    corners = ensure_demo_corners()
    medicines = ensure_demo_medicines(users)
    analytics = calculate_demo_analytics()
    return {
        "users": users,
        "corners": corners,
        "medicines": medicines,
        "analytics": analytics,
        "summary": demo_summary(),
    }


@transaction.atomic
def delete_demo_dataset():
    """Delete demo-generated data while preserving superusers and non-demo data."""
    demo_users = User.objects.filter(is_demo_account=True, is_superuser=False)
    demo_user_ids = list(demo_users.values_list("id", flat=True))
    medicines = Medicine.objects.filter(
        Q(batch_number__startswith=DEMO_BATCH_PREFIX)
        | Q(donor_id__in=demo_user_ids)
        | Q(patient_id__in=demo_user_ids)
    )
    counts = {
        "medicines": medicines.count(),
        "regular_users": demo_users.exclude(role=User.Role.PHARMACIST).count(),
        "pharmacists": demo_users.filter(role=User.Role.PHARMACIST).count(),
        "corners": ReMediCorner.objects.filter(name__startswith=DEMO_CORNER_PREFIX).count(),
        "preserved_superusers": User.objects.filter(is_superuser=True).count(),
    }
    medicines.delete()
    ReMediCorner.objects.filter(name__startswith=DEMO_CORNER_PREFIX).delete()
    demo_users.delete()
    return counts


def reset_demo_dataset():
    """Delete and recreate the full demo dataset."""
    deleted = delete_demo_dataset()
    seeded = seed_demo_dataset()
    return {
        "deleted": deleted,
        **seeded,
    }


def is_seeded_demo_data_ready():
    return Medicine.objects.filter(batch_number__startswith=DEMO_BATCH_PREFIX).exists()
