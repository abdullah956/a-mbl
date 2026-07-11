












# Implementation notes — version 0.1

This documents what is actually built, how to run it, and where it deviates
from [MOBILE_APP_ROADMAP.md](MOBILE_APP_ROADMAP.md) (and why). Nothing here
claims production readiness, measured accuracy, or legal compliance.

## What works end to end

- **Backend** (`backend/`): FastAPI + SQLite with every `/v1` endpoint from
  roadmap §10 — health, register/login/refresh/logout/me, guardian link codes
  and approval, organizations and members, `/v1/analyses`, `/v1/ocr`
  (feature-flagged), cases with human reviews / evidence / organization
  shares, alerts, summary reports, masked PDF, data export, account deletion.
- **Policy**: five primary labels + Body Shaming tag; severity mapping;
  `needsReview` below 0.70 confidence; alerts only for High/Critical
  harassment / hate speech / threat at ≥ 0.80 confidence; Offensive and the
  Body Shaming tag alone never alert (§6.3, §14.1, §19).
- **Privacy**: Normal raw text is never stored (tests scan the SQLite file
  bytes to prove it); harmful text and evidence are Fernet-encrypted; masked
  previews are computed on demand rather than stored; cases expire after 30
  days via a cleanup job at startup + every 24 h; account deletion cascades
  rows and removes evidence files; alert previews carry no content.
- **Mobile** (`mobile/`, Expo SDK 57 + expo-router + TypeScript): connection
  screen with editable server address and health check, neutral age screen,
  register/login, pending-approval screen with link code, five tabs
  (Home/Analyze/Cases/Alerts/Profile), text analysis with inline result,
  screenshot → OCR → correct → analyze flow (hidden when the server lacks
  Tesseract), case detail with deliberate **Reveal**, human reviews,
  organization sharing with named confirmation, evidence attach/view,
  guardian linking, data export, account deletion.
- **Tests**: 86 pytest cases (`backend/tests/`) covering auth (including
  token tampering and expired refresh), age gate, link codes, IDOR and
  cross-organization isolation, retention, encryption, alert scoping and
  cleanup on revocation, report/PDF role scoping and masking, OCR validation,
  and the classifier against `tests/fixtures/labeled_samples.jsonl`
  (including punctuation, obfuscation, and phantom-match regressions).
  Mobile is TypeScript-strict and verified to bundle with `expo export`.

## How to run

Backend (once): `conda create -n a-mbl python=3.11 -y`, then
`conda activate a-mbl && pip install -r backend/requirements.txt`.

```bash
# from the repository root
conda activate a-mbl
python -m pytest backend/tests            # test suite
python -m backend.scripts.seed_demo       # synthetic demo accounts (see below)
./backend/run.sh                          # serve on 0.0.0.0:8000 for phones
```

Mobile: `cd mobile && npm install && npx expo start`, open in Expo Go, and on
the first screen enter the address `run.sh` printed (e.g.
`http://192.168.1.20:8000`).

School admin accounts (invitation-only, §5.3):
`python -m backend.scripts.create_admin "School name" email password "Display name"`.

Demo accounts after seeding (password `demo-pass-123`): `demo.user@a-mbl.test`,
`demo.guardian@a-mbl.test`, `demo.teen@a-mbl.test` (linked to the guardian),
`demo.admin@a-mbl.test` (Demo High School).

## Deviations from the roadmap, with reasons

| Roadmap                                           | v0.1 choice                                                                  | Why                                                                                                                                             |
| ------------------------------------------------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Trained TF-IDF + Logistic Regression model (§12) | Deterministic lexicon baseline`lexicon-0.1.0` behind the same interface    | No dataset work has happened yet; a fake "trained" model would violate §18.5 honesty rules. The swap-in path is documented in`ml/README.md`. |
| Argon2 password hashing (§16.3)                  | PBKDF2-HMAC-SHA256 (210k iterations, stdlib)                                 | Zero native dependencies for the local prototype; interchangeable later because hashes are versioned strings.                                   |
| SQLAlchemy 2 + Alembic (§9.2)                    | Plain`sqlite3` with `CREATE TABLE IF NOT EXISTS`                         | One less layer for a single-file local DB; the schema lives in one place (`backend/app/db.py`).                                               |
| TanStack Query, React Hook Form, Zod (§9.1)      | Plain React state + a small typed fetch wrapper                              | Fewer moving parts for the first working version; screens are small enough to stay readable.                                                    |
| OpenAPI-generated TS types (§10)                 | Hand-mirrored`mobile/src/lib/types.ts`                                     | Type generation is worth adding once the contract stops moving; the FastAPI OpenAPI doc remains the source of truth.                            |
| Role-specific tab sets (§8.2–8.4)               | One five-tab layout whose titles and content adapt per role                  | Same information scope, less navigation code; backend scoping is what enforces access anyway (§5.4).                                           |
| PDF download inside the app (§15.2)              | PDF served by`POST /v1/reports/pdf`; mobile shows the summary screen       | Saving/sharing files in Expo Go needs extra packages; the masked PDF itself works and is tested.                                                |
| Tesseract OCR always on (§13)                    | Feature flag:`/v1/health.ocrReady`; the app hides the scan flow when false | Tesseract is a system binary that may not be installed (`brew install tesseract`). Upload validation still runs and is tested either way.     |

## Known limitations

- The lexicon classifier misses anything outside its word lists and has no
  measured accuracy; treat every result as the uncertain estimate the UI says
  it is.
- Local HTTP on a shared Wi-Fi network only; synthetic content only (§16.4).
- In-app alerts refresh when the tab gains focus or on pull-to-refresh; there
  are no push notifications by design (§4.2).
- Evidence viewing streams through an authorized URL with the current access
  token; if the token has expired the screen shows a "Try again" action that
  refreshes the session and reloads the image.
