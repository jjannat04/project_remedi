from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from myapp.models import Medicine, User
from myapp.services.qr import ensure_medicine_qr


HISTORY_BATCH_PREFIX = "RMD-HIST-"
HISTORY_PASSWORD = "remedi-history-4567"


DONORS = (
    ("hist_donor_amina", "amina.history@remedi.local", "Amina", "Rahman", "01721001001"),
    ("hist_donor_rashed", "rashed.history@remedi.local", "Rashed", "Karim", "01721001002"),
    ("hist_donor_sadia", "sadia.history@remedi.local", "Sadia", "Akter", "01721001003"),
    ("hist_donor_tanvir", "tanvir.history@remedi.local", "Tanvir", "Hasan", "01721001004"),
    ("hist_donor_nusrat", "nusrat.history@remedi.local", "Nusrat", "Jahan", "01721001005"),
    ("hist_donor_fahim", "fahim.history@remedi.local", "Fahim", "Mahmud", "01721001006"),
)

PATIENTS = (
    ("hist_patient_arif", "arif.history@remedi.local", "Arif", "Hossain", "01722002001"),
    ("hist_patient_lamia", "lamia.history@remedi.local", "Lamia", "Chowdhury", "01722002002"),
    ("hist_patient_riyad", "riyad.history@remedi.local", "Riyad", "Khan", "01722002003"),
    ("hist_patient_nabila", "nabila.history@remedi.local", "Nabila", "Karim", "01722002004"),
    ("hist_patient_mehedi", "mehedi.history@remedi.local", "Mehedi", "Islam", "01722002005"),
    ("hist_patient_farzana", "farzana.history@remedi.local", "Farzana", "Begum", "01722002006"),
    ("hist_patient_shuvo", "shuvo.history@remedi.local", "Shuvo", "Das", "01722002007"),
    ("hist_patient_tania", "tania.history@remedi.local", "Tania", "Sultana", "01722002008"),
)

PHARMACISTS = (
    ("hist_pharm_samira", "samira.history@remedi.local", "Dr. Samira", "Haque", "BPC-HIST-2101"),
    ("hist_pharm_ashik", "ashik.history@remedi.local", "Dr. Ashik", "Sen", "BPC-HIST-2102"),
    ("hist_pharm_farhan", "farhan.history@remedi.local", "Dr. Farhan", "Kabir", "BPC-HIST-2103"),
)

VERIFIED_DONATIONS = (
    ("Napa 500 mg Tablet", "Paracetamol", "500 mg", "Beximco Pharmaceuticals", "Pain relief", "strip", "cool_dry", 4, "180.00"),
    ("Seclo 20 Capsule", "Omeprazole", "20 mg", "Square Pharmaceuticals", "Digestive health", "box", "room_temperature", 2, "320.00"),
    ("DP-Met 500 Tablet", "Metformin Hydrochloride", "500 mg", "Drug International", "Diabetes", "strip", "cool_dry", 3, "540.00"),
    ("Amdocal 5 Tablet", "Amlodipine", "5 mg", "Beximco Pharmaceuticals", "Hypertension", "strip", "room_temperature", 2, "330.00"),
    ("Montene 10 Tablet", "Montelukast", "10 mg", "Aristopharma", "Respiratory", "strip", "cool_dry", 1, "390.00"),
    ("Ceevit Tablet", "Vitamin C", "250 mg", "Square Pharmaceuticals", "Vitamins", "strip", "cool_dry", 6, "160.00"),
    ("Fexo 120 Tablet", "Fexofenadine", "120 mg", "Beximco Pharmaceuticals", "Allergy", "strip", "room_temperature", 2, "350.00"),
    ("Calbo-D Tablet", "Calcium + Vitamin D3", "500 mg", "Square Pharmaceuticals", "Vitamins", "box", "cool_dry", 3, "280.00"),
    ("Bisocor 2.5 Tablet", "Bisoprolol", "2.5 mg", "Incepta Pharmaceuticals", "Hypertension", "strip", "cool_dry", 1, "410.00"),
    ("DP-Rab 20 Tablet", "Rabeprazole Sodium", "20 mg", "Drug International", "Digestive health", "strip", "cool_dry", 2, "460.00"),
    ("Salmolin Inhaler", "Salbutamol", "100 mcg", "Acme Laboratories", "Respiratory", "injection", "room_temperature", 1, "420.00"),
    ("Ace 500 Tablet", "Paracetamol", "500 mg", "Square Pharmaceuticals", "Pain relief", "strip", "room_temperature", 5, "170.00"),
    ("Glucored 80 Tablet", "Gliclazide", "80 mg", "Eskayef", "Diabetes", "strip", "cool_dry", 2, "370.00"),
    ("Losardil 50 Tablet", "Losartan Potassium", "50 mg", "Square Pharmaceuticals", "Hypertension", "strip", "room_temperature", 3, "400.00"),
    ("Napa Syrup", "Paracetamol", "120 mg/5 ml", "Beximco Pharmaceuticals", "Children", "bottle", "room_temperature", 1, "150.00"),
    ("Tofen Syrup", "Ketotifen", "1 mg/5 ml", "Square Pharmaceuticals", "Children", "bottle", "room_temperature", 1, "210.00"),
    ("Maxpro 20 Tablet", "Esomeprazole", "20 mg", "Renata Limited", "Digestive health", "strip", "cool_dry", 2, "360.00"),
    ("Cef-3 200 Capsule", "Cefixime", "200 mg", "Square Pharmaceuticals", "Antibiotic", "box", "room_temperature", 1, "720.00"),
    ("Azithrocin 500 Tablet", "Azithromycin", "500 mg", "Acme Laboratories", "Antibiotic", "strip", "cool_dry", 1, "790.00"),
    ("Monas 10 Tablet", "Montelukast", "10 mg", "Acme Laboratories", "Respiratory", "strip", "cool_dry", 2, "480.00"),
    ("Cardobis 5 Tablet", "Bisoprolol", "5 mg", "Incepta Pharmaceuticals", "Hypertension", "strip", "cool_dry", 2, "430.00"),
    ("ORS Saline-N", "Oral Rehydration Salts", "10.25 g", "Social Marketing Company", "Children", "box", "cool_dry", 8, "120.00"),
    ("Sitagil M Tablet", "Sitagliptin + Metformin", "50/500 mg", "Incepta Pharmaceuticals", "Diabetes", "strip", "cool_dry", 1, "690.00"),
    ("Multivit Plus Tablet", "Multivitamin", "Once daily", "Healthcare Pharma", "Vitamins", "box", "cool_dry", 4, "450.00"),
    ("DP-Vent Inhaler", "Salbutamol", "100 mcg", "Drug International", "Respiratory", "injection", "room_temperature", 1, "510.00"),
)

REJECTED_DONATIONS = (
    ("Losectil 20 Capsule", "Omeprazole", "20 mg", "Eskayef", "Digestive health", "Outer strip seal is damaged and cannot be verified safely."),
    ("Expired Napa Syrup", "Paracetamol", "120 mg/5 ml", "Beximco Pharmaceuticals", "Children", "Expiry date is too close and the bottle appears opened."),
    ("DP-Clox Capsule", "Cloxacillin", "500 mg", "Drug International", "Antibiotic", "Water damage marks are visible on the carton."),
    ("Unclear Insulin Pen", "Insulin Glargine", "100 IU/ml", "Unknown", "Diabetes", "Label and batch number are unreadable."),
    ("Tampered Cefixime Box", "Cefixime", "400 mg", "Unknown", "Antibiotic", "Possible tampered seal and counterfeit warning signs."),
    ("Blurry Zimax Tablet", "Azithromycin", "500 mg", "Square Pharmaceuticals", "Antibiotic", "Uploaded package details were insufficient for pharmacist verification."),
    ("Opened Antacid Bottle", "Aluminium Hydroxide + Magnesium Hydroxide", "200/400 mg", "Acme Laboratories", "Digestive health", "Bottle was previously opened and storage history is uncertain."),
    ("Damaged Insulet R", "Regular Insulin", "100 IU/ml", "Incepta Pharmaceuticals", "Diabetes", "Cold-chain storage could not be confirmed."),
    ("Loose Pain Tablets", "Ibuprofen", "400 mg", "Unknown", "Pain relief", "Medicine was not in original packaging."),
    ("Faded Batch Antibiotic", "Amoxicillin", "500 mg", "Unknown", "Antibiotic", "Batch and expiry text are faded beyond reliable review."),
)

PENDING_DONATIONS = (
    ("Kids Cold Syrup", "Chlorpheniramine + Phenylephrine", "2 mg/5 ml", "Acme Laboratories", "Children"),
    ("Near Expiry Zinc", "Zinc Sulfate", "20 mg", "Renata Limited", "Vitamins"),
    ("Insulet R Injection", "Regular Insulin", "100 IU/ml", "Incepta Pharmaceuticals", "Diabetes"),
    ("Zimax 500 Tablet", "Azithromycin", "500 mg", "Square Pharmaceuticals", "Antibiotic"),
    ("DP-Cal D Tablet", "Calcium + Vitamin D3", "500 mg", "Drug International", "Vitamins"),
)

LOCATIONS = (
    ("Dhanmondi", "Dhaka", "House 42, Road 7A, Dhanmondi, Dhaka"),
    ("Uttara", "Dhaka", "Sector 7, Rabindra Sarani, Uttara, Dhaka"),
    ("Mirpur", "Dhaka", "Section 10, Mirpur, Dhaka"),
    ("Agrabad", "Chattogram", "Sheikh Mujib Road, Agrabad, Chattogram"),
    ("Feni Sadar", "Feni", "S S K Road, Feni Sadar, Feni"),
    ("Zindabazar", "Sylhet", "Zindabazar Point, Sylhet"),
)


def historical_time(days_ago, hour):
    return (timezone.now() - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0)


def expiry_date(months_ahead):
    return (timezone.now().date() + timedelta(days=30 * months_ahead)).replace(day=1)


def get_or_create_history_user(username, email, first_name, last_name, role, phone, license_number=""):
    user = User.objects.filter(username=username).first() or User.objects.filter(email=email).first()
    if user:
        return user, False

    user = User.objects.create_user(
        username=username,
        email=email,
        password=HISTORY_PASSWORD,
        first_name=first_name,
        last_name=last_name,
        role=role,
        phone=phone,
        license_number=license_number,
        is_demo_account=True,
        is_active=True,
    )
    return user, True


class Command(BaseCommand):
    help = "One-time utility that adds historical demo donation records without touching marketplace medicines."

    @transaction.atomic
    def handle(self, *args, **options):
        if Medicine.objects.filter(batch_number__startswith=HISTORY_BATCH_PREFIX).exists():
            count = Medicine.objects.filter(batch_number__startswith=HISTORY_BATCH_PREFIX).count()
            self.stdout.write(
                self.style.WARNING(
                    f"Historical demo records already exist ({count} medicines). No new data was created."
                )
            )
            return

        donors = [
            get_or_create_history_user(username, email, first, last, User.Role.DONOR, phone)[0]
            for username, email, first, last, phone in DONORS
        ]
        patients = [
            get_or_create_history_user(username, email, first, last, User.Role.PATIENT, phone)[0]
            for username, email, first, last, phone in PATIENTS
        ]
        pharmacists = [
            get_or_create_history_user(username, email, first, last, User.Role.PHARMACIST, "01723003001", license_number)[0]
            for username, email, first, last, license_number in PHARMACISTS
        ]

        created_medicines = []
        for index, row in enumerate(VERIFIED_DONATIONS, start=1):
            submitted_at = historical_time(182 - (index * 6), 9)
            verified_at = submitted_at + timedelta(hours=5)
            ordered_at = verified_at + timedelta(days=2, hours=2)
            completed_at = ordered_at + timedelta(days=1, hours=3)
            pharmacist = pharmacists[index % len(pharmacists)]
            location = LOCATIONS[index % len(LOCATIONS)]

            medicine = Medicine.objects.create(
                donor=donors[index % len(donors)],
                patient=patients[index % len(patients)],
                name=row[0],
                scientific_name=row[1],
                dosage=row[2],
                manufacturer=row[3],
                category=row[4],
                batch_number=f"{HISTORY_BATCH_PREFIX}APP-{index:03d}",
                expiry_date=expiry_date(8 + index % 16),
                original_price=Decimal(row[8]),
                status="sold",
                is_physical_intact=True,
                is_authentic=True,
                is_expiry_valid=True,
                verified_at=verified_at,
                completed_at=completed_at,
                ordered_at=ordered_at,
                reserved_until=None,
                quantity=0,
                package_type=row[5],
                opened=False,
                storage_condition=row[6],
                donor_phone=donors[index % len(donors)].phone,
                area=location[0],
                district=location[1],
                donation_address=location[2],
                pickup_notes=(
                    f"Historical demo review approved by {pharmacist.get_full_name()} "
                    f"({pharmacist.license_number}) on {verified_at.date().isoformat()}."
                ),
            )
            ensure_medicine_qr(medicine)
            created_medicines.append(medicine)

        for index, row in enumerate(REJECTED_DONATIONS, start=1):
            submitted_at = historical_time(176 - (index * 8), 10)
            rejected_at = submitted_at + timedelta(hours=4)
            pharmacist = pharmacists[index % len(pharmacists)]
            location = LOCATIONS[(index + 2) % len(LOCATIONS)]

            created_medicines.append(Medicine.objects.create(
                donor=donors[(index + 1) % len(donors)],
                name=row[0],
                scientific_name=row[1],
                dosage=row[2],
                manufacturer=row[3],
                category=row[4],
                batch_number=f"{HISTORY_BATCH_PREFIX}REJ-{index:03d}",
                expiry_date=expiry_date(2 + index % 10),
                original_price=Decimal("260.00") + Decimal(index * 35),
                status="rejected",
                is_physical_intact=index % 3 != 0,
                is_authentic=index % 4 != 0,
                is_expiry_valid=index % 2 != 0,
                rejected_at=rejected_at,
                rejection_reason=row[5],
                quantity=0,
                package_type="box" if index % 2 else "strip",
                opened=True,
                storage_condition="unknown",
                donor_phone=donors[(index + 1) % len(donors)].phone,
                area=location[0],
                district=location[1],
                donation_address=location[2],
                pickup_notes=(
                    f"Historical demo review rejected by {pharmacist.get_full_name()} "
                    f"({pharmacist.license_number}) on {rejected_at.date().isoformat()}."
                ),
            ))

        for index, row in enumerate(PENDING_DONATIONS, start=1):
            location = LOCATIONS[(index + 4) % len(LOCATIONS)]
            created_medicines.append(Medicine.objects.create(
                donor=donors[(index + 2) % len(donors)],
                name=row[0],
                scientific_name=row[1],
                dosage=row[2],
                manufacturer=row[3],
                category=row[4],
                batch_number=f"{HISTORY_BATCH_PREFIX}PEN-{index:03d}",
                expiry_date=expiry_date(6 + index),
                original_price=Decimal("220.00") + Decimal(index * 55),
                status="pending",
                is_physical_intact=index % 2 == 0,
                is_authentic=index == 2,
                is_expiry_valid=index % 2 != 0,
                quantity=1,
                package_type="bottle" if "Syrup" in row[0] else "strip",
                opened=False,
                storage_condition="refrigerated" if "Insulet" in row[0] else "cool_dry",
                donor_phone=donors[(index + 2) % len(donors)].phone,
                area=location[0],
                district=location[1],
                donation_address=location[2],
                pickup_notes=(
                    "Historical demo pending review. Submission date is represented by the "
                    "surrounding review timeline because Medicine has no created_at field."
                ),
            ))

        historical = Medicine.objects.filter(batch_number__startswith=HISTORY_BATCH_PREFIX)
        self.stdout.write("Historical demo population complete:")
        self.stdout.write(f"- medicines created: {len(created_medicines)}")
        self.stdout.write(f"- verified/completed history: {historical.filter(status='sold').count()}")
        self.stdout.write(f"- rejected history: {historical.filter(status='rejected').count()}")
        self.stdout.write(f"- pending review history: {historical.filter(status='pending').count()}")
        self.stdout.write(f"- QR codes generated: {historical.filter(qr_code_id__isnull=False).exclude(qr_code_id='').count()}")
        self.stdout.write(
            self.style.SUCCESS(
                "Existing marketplace medicines, images, schema, URLs, templates, and services were not modified."
            )
        )
