# Seeded Demo Data

## Purpose

`python manage.py seed_demo` creates a deterministic, offline dataset for judging ReMedi end to end. It uses the existing single Django app, normal models, Django templates, and the same server-rendered pages as the rest of the product.

## Demo Users

The seed command creates or refreshes these users:

- Demo Donor: `demo_donor@remedi.local`
- Demo Central Pharmacist: `demo_pharmacist@remedi.local`
- Demo Patient: `demo_patient@remedi.local`

All three users are marked with `is_demo_account=True`, use the existing role field, and are active. The internal deterministic password is used only by the seed/login foundation; judges do not need to know it.

## Demo Medicines

Seeded medicines use deterministic `RMD-DEMO-...` batch numbers and fixed UUID values. Running the command repeatedly updates these records instead of creating duplicates.

- Pending Verification: `Napa 500 mg Tablet`, scientific name `Paracetamol`, batch `RMD-DEMO-PENDING-001`
- Verified Marketplace: `Cef-3 200 mg Capsule`, scientific name `Cefixime`, batch `RMD-DEMO-VERIFIED-001`
- Verified Marketplace: `DP-Met 500 mg Tablet`, scientific name `Metformin Hydrochloride`, batch `RMD-DEMO-VERIFIED-002`
- Verified Marketplace: `Montene 10 mg Tablet`, scientific name `Montelukast`, batch `RMD-DEMO-VERIFIED-003`
- Rejected: `Losectil 20 mg Capsule`, scientific name `Omeprazole`, batch `RMD-DEMO-REJECTED-001`
- Reserved: `Amdocal 5 mg Tablet`, scientific name `Amlodipine`, batch `RMD-DEMO-RESERVED-001`
- Sold/Completed: `DP-Rab 20 mg Tablet`, scientific name `Rabeprazole Sodium`, batch `RMD-DEMO-SOLD-001`

## Statuses Represented

- `pending`: waiting in the pharmacist verification queue.
- `verified` with no patient: visible as available marketplace inventory.
- `rejected`: has a rejection reason and rejected timestamp.
- `verified` with a patient and no completion timestamp: reserved for the demo patient and excluded from available inventory.
- `sold`: completed redistribution with buyer, ordered timestamp, and completion timestamp.

## Analytics

Demo analytics are computed from medicines where either the donor or patient is a demo account:

- Medicines donated: count of demo medicines.
- Medicines verified: count of medicines with `verified` or `sold` status.
- Medicines rejected: count of medicines with `rejected` status.
- Medicines redistributed/sold: count of medicines with `sold` status.
- Estimated savings: sum of `original_price - resale_price` for sold medicines.
- Waste prevented count: count of verified or sold medicines.
- Patients helped count: distinct patients attached to reserved or sold demo medicines.

## Reset And Reseed

To refresh the deterministic data:

```powershell
python manage.py seed_demo
```

To fully reset demo medicine records before reseeding, delete records with batch numbers beginning `RMD-DEMO-`, then run:

```powershell
python manage.py seed_demo
```

The command does not call AI, Gemini, OCR, QR generation, OTP, upload flows, background workers, APIs, or external services.
