# Demo Mode

Demo mode prepares ReMedi for judge-friendly presentations while keeping the current single Django app and server-rendered template architecture intact.

## Purpose

Demo mode is a lightweight configuration layer for showcasing the product with predictable data and flows. It does not bypass authentication, create seed data, call AI services, generate QR codes, or change marketplace behavior yet.

## Judge Workflow

Judges can start at `/judge/`, which is a public entry page. The page introduces the demo and shows entry points for a demo donor and a demo central pharmacist. These buttons are placeholders for now and do not log anyone in.

## Future Seeded Data Plans

Future work can add deterministic seeded users, medicines, orders, verification queues, and savings metrics. Demo accounts should use the `is_demo_account` flag so they can be identified and managed separately from normal users.

## Fallback Philosophy

Demo features should remain dependable even when optional external services are unavailable. Future AI or QR integrations should use service-layer wrappers and honor `AI_FALLBACK_ENABLED` so the judge experience can continue with deterministic fallback behavior.
