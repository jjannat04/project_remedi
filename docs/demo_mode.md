# Demo Mode

Demo mode prepares ReMedi for judge-friendly presentations while keeping the current single Django app and server-rendered template architecture intact.

## Purpose

Demo mode is a lightweight configuration layer for showcasing the product with predictable data and flows. It can seed deterministic demo accounts and offers judge-only entry actions that still use Django authentication sessions. It does not call AI services, generate QR codes, or change marketplace behavior.

## Judge Workflow

Judges can start at `/judge/` when `DEMO_MODE=True`. The page introduces the demo and shows entry points for a demo donor and a demo central pharmacist, each backed by a real Django login session.

## Future Seeded Data Plans

The current seed command creates deterministic demo users and basic account placeholders only. Future work can add medicines, orders, verification queues, and savings metrics. Demo accounts use the `is_demo_account` flag so they can be identified and managed separately from normal users.

## Fallback Philosophy

Demo features should remain dependable even when optional external services are unavailable. Future AI or QR integrations should use service-layer wrappers and honor `AI_FALLBACK_ENABLED` so the judge experience can continue with deterministic fallback behavior.
