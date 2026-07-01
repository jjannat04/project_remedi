# Judge Login Bypass

## Purpose

The judge bypass gives evaluators a fast way to enter ReMedi as deterministic demo users while still using normal Django authentication and session handling. It keeps the current single Django app, server-rendered templates, and existing login/signup flows.

## Seeded Accounts

Run `python manage.py seed_demo` to create or refresh:

- Demo Donor: `demo_donor@remedi.local`
- Demo Central Pharmacist: `demo_pharmacist@remedi.local`

Both users are marked with `is_demo_account=True`, use the existing role field, and are active. The command is idempotent, so it is safe to run repeatedly.

## Login Flow

When `DEMO_MODE=True`, `/judge/` shows two POST buttons:

- `Enter as Demo Donor` signs in the donor demo account and redirects to the donor profile page.
- `Enter as Demo Central Pharmacist` signs in the pharmacist demo account and redirects to the pharmacist dashboard.

The buttons call Django `login()` so the result is a real authenticated Django session. Judges do not need the deterministic internal password.

## Security Restrictions

The `/judge/` page and demo login actions are only available when `DEMO_MODE=True`. When `DEMO_MODE=False`, these routes return 404 and no demo login is possible.

The bypass does not create medicines, analytics data, marketplace data, QR codes, OTP flows, AI output, background jobs, APIs, or any non-demo user accounts.

## Why Demo Mode Only

The bypass exists only for controlled judging and local demo environments. Keeping it behind `DEMO_MODE` prevents passwordless entry from being available in normal or production-like operation.
