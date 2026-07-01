# Demo Mode

Demo mode prepares ReMedi for judge-friendly presentations while keeping the current single Django app and server-rendered template architecture intact.

## Purpose

Demo mode is a lightweight configuration layer for showcasing the product with predictable data and flows. It can seed deterministic demo accounts, medicines, and simple analytics, and it offers judge-only entry actions that still use Django authentication sessions. It does not call AI services, generate QR codes, or require external services.

## Judge Workflow

Judges can start at `/judge/` when `DEMO_MODE=True`. The page introduces the demo and shows entry points for a demo donor and a demo central pharmacist, each backed by a real Django login session.

## Seeded Data

The current seed command creates deterministic demo users, pending/verified/rejected/reserved/sold medicines, and simple SSR dashboard metrics. Demo accounts use the `is_demo_account` flag so they can be identified and managed separately from normal users. See `docs/seeded_demo_data.md` for details.

## Fallback Philosophy

Demo features should remain dependable even when optional external services are unavailable. Future AI or QR integrations should use service-layer wrappers and honor `AI_FALLBACK_ENABLED` so the judge experience can continue with deterministic fallback behavior.
