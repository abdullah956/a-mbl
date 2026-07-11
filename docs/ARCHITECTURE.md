# a-mbl architecture and workflow

How the system fits together, how a request flows through it, and how to work
on it day to day. The product spec is [MOBILE_APP_ROADMAP.md](MOBILE_APP_ROADMAP.md);
deviations and their reasons are in [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md);
run instructions are in [HOW_TO_RUN.md](HOW_TO_RUN.md).

## 1. System overview

```text
┌─────────────────────────────┐        same Wi-Fi         ┌──────────────────────────────────┐
│  Phone (Expo Go)            │   JSON + multipart HTTP   │  Mac                             │
│                             │ ───────────────────────►  │                                  │
│  mobile/ — Expo Router app  │                           │  backend/ — FastAPI (uvicorn)    │
│  · SecureStore: refresh     │  ◄───────────────────────  │  · auth / roles / scoping        │
│    token + server address   │        /v1 responses      │  · lexicon classifier + policy   │
│  · access token in memory   │                           │  · OCR (Tesseract, optional)     │
│  · no analyzed content      │                           │  · reports (ReportLab PDF)       │
│    persisted on device      │                           │  · retention cleanup (24 h)      │
└─────────────────────────────┘                           │        │                         │
                                                          │        ▼                         │
                                                          │  backend/data/  (gitignored)     │
                                                          │  · a_mbl.sqlite3 (SQLite, FKs)   │
                                                          │  · signing.key / fernet.key      │
                                                          │  · evidence/*.bin (encrypted)    │
                                                          └──────────────────────────────────┘
```

There is no cloud, no push notifications, and no background monitoring — the
user submits content explicitly, and alerts are rows the app polls when the
Alerts tab gains focus.

## 2. Backend layout (`backend/app/`)

| Module | Responsibility |
| --- | --- |
| `main.py` | App factory, CORS, router registration, lifespan (model version registration + retention cleanup at startup and every 24 h) |
| `config.py` | All tunables: token lifetimes, 30-day retention, size limits, 0.70/0.80 confidence thresholds, data directory |
| `db.py` | SQLite schema (14 tables), per-request connection dependency (commit on success, rollback on error), id/time helpers, audit writer |
| `security.py` | PBKDF2 password hashing, HMAC-signed 15-min access tokens, rotating 7-day refresh tokens (stored as SHA-256 hashes), Fernet encryption for case text/notes/evidence |
| `classifier.py` + `lexicon.py` | Deterministic `lexicon-0.1.0` model: normalization (lowercase, leet-speak, repeat-collapse), word-boundary phrase matching per category, heuristic confidence, matched terms for masking |
| `policy.py` | Severity mapping (§6.2), Body Shaming floor to High, `needsReview` < 0.70, alert eligibility, cautious advice strings |
| `deps.py` | `current_user` / `active_user` auth dependencies and `case_scope()` — the single SQL fragment that enforces the §5.4 permission matrix on every case query |
| `errors.py` | The uniform `{code, message, fieldErrors?, requestId}` error body for every non-success response |
| `ocr.py` | Magic-byte + Pillow validation, then Tesseract if installed (`/v1/health.ocrReady` feature flag) |
| `pdf.py` | In-memory masked PDF (no temp files) |
| `retention.py` | Expired-case deletion (files first, then rows), stale code/token purge |
| `routers/` | One file per API area: `health`, `auth`, `links`, `analysis`, `cases`, `alerts`, `reports`, `privacy` |

`backend/scripts/`: `create_admin.py` (invitation-only school-admin accounts),
`seed_demo.py` (synthetic demo data).

## 3. Mobile layout (`mobile/src/`)

| Path | Responsibility |
| --- | --- |
| `lib/api.ts` | Typed fetch wrapper: base URL + refresh token in SecureStore, access token in memory, single-flight refresh with one retry on 401, uniform `ApiError` |
| `lib/auth.tsx` | `AuthProvider`: restores the session from the refresh token at boot, exposes `signIn/register/signOut/reloadUser` |
| `lib/types.ts` | Hand-mirrored API contract types (source of truth: FastAPI's `/docs`) |
| `lib/theme.ts` | Pastel palette, severity metadata (icon + label + colors — never color alone), date/percent formatters |
| `components/ui.tsx` | Screen/Card/Button/Field/Banner/SeverityChip/etc. — 48pt touch targets, accessibility labels |
| `app/index.tsx` | Boot router: no server → `/connect`; no session → welcome; pending → `/pending`; else tabs |
| `app/connect.tsx` | Editable server address + `/v1/health` check with troubleshooting hints |
| `app/(auth)/` | `welcome` → `age` (neutral month/year gate, under-13 stops with nothing saved) → `register` / `login` |
| `app/pending.tsx` | 13–17 waiting room: shows/regenerates the one-time guardian code, re-checks status |
| `app/(tabs)/` | `index` (role-scoped summary), `analyze` (text + screenshot→OCR→correct→analyze), `cases` (filterable list), `alerts` (content-free inbox), `profile` (links, privacy, sign-out) |
| `app/case/[id].tsx` | Case detail: deliberate **Reveal**, human reviews, named-confirmation org sharing, encrypted evidence attach/view, delete |

## 4. Key flows

### Text analysis (§7.2)

```text
Analyze tab ──POST /v1/analyses {text, sourceType, platformName?, senderAlias?}──►
  classifier.classify(text)  →  label, confidence, bodyShaming, matched terms
  policy: severity, needsReview(<0.70), advice
  INSERT analysis_events      (metadata only — never the text)
  severity != safe?
    ├─ yes → INSERT flagged_cases (Fernet-encrypted text, expires +30 days)
    │        alert-eligible (harassment/hate/threat, High/Critical, conf ≥ 0.80)?
    │          └─ yes → INSERT OR IGNORE alerts for owner + actively linked guardians
    └─ no  → nothing stored; raw text discarded with the request
◄── AnalysisResult {label, confidence, severity, needsReview, advice[], caseId?, retainedUntil?}
```

### Screenshot analysis (§7.3)

```text
pick camera/gallery (permission asked only then, EXIF stripped, re-encoded)
  → POST /v1/ocr (multipart "file")
      validate magic bytes + Pillow decode + ≤10 MB + ≤6000 px   (413/422 on failure)
      Tesseract → {text, meanConfidence, lowConfidence}          (503 if not installed)
  → user reviews/corrects the text in the editable field
  → same POST /v1/analyses as above with sourceType="screenshot"
The image is processed in memory and never retained unless the user later
attaches it to a case via POST /v1/cases/{id}/evidence (stored Fernet-encrypted).
```

### Guardian linking (§7.1)

```text
13–17 registration → account status pending_guardian + one-time 8-char code (24 h, hashed)
guardian enters code → POST /v1/guardian-links/accept
  → guardian_links row (active) + code consumed + teen account activated
either side revokes → link status revoked → guardian's case access ends immediately
```

### Organization sharing (§7.4)

```text
owner picks org → named confirmation → POST /v1/cases/{id}/shares
  → case_shares row + alerts for that org's admins (if the case is alert-eligible)
owner revokes → share.revoked_at set + that org's alerts for the case deleted
  → admins lose access on their very next query (scope checks revoked_at IS NULL)
```

### Authentication

```text
login/register → access token (HMAC-signed payload, 15 min, in memory)
              +  refresh token (random, 7 days, SHA-256 hash in DB, SecureStore on device)
API 401 → single-flight POST /v1/auth/refresh → rotate: old token revoked + replaced_by set
reuse of a rotated token → ALL of that user's refresh tokens revoked (stolen-token defense)
```

## 5. Data model (SQLite, foreign keys ON)

```text
users ─┬─< refresh_tokens
       ├─< guardian_link_codes         (hashed one-time codes)
       ├─< guardian_links >─ users     (user ⇄ guardian, status active/revoked)
       ├─< organization_memberships >─ organizations
       ├─< analysis_events             (label/confidence/severity metadata; NEVER raw text)
       │      └─ 1:1 flagged_cases     (Fernet-encrypted text, 30-day expires_at)
       │             ├─< case_evidence (encrypted file on disk, hash, mime)
       │             ├─< case_shares >─ organizations (revocable)
       │             ├─< review_events (human label + encrypted note; model row untouched)
       │             └─< alerts        (recipient, severity, category — no content)
       └   model_versions, audit_events (no content, no secrets)
```

Deleting a user cascades to everything they own; deleting a case cascades to
evidence/shares/reviews/alerts, with evidence files unlinked first.

## 6. Security and privacy design

- **Authorization lives in SQL, not in screens.** Every case/report/alert query
  passes through `deps.case_scope(user)`: owners see their own; guardians add
  actively-linked users; school admins add unrevoked shares to their org.
  Unauthorized access returns 404 (existence is not revealed).
- **Data minimization**: normal text never persisted (tests scan the raw DB
  file bytes); harmful text/evidence/notes only as Fernet ciphertext; masked
  previews computed on demand, never stored; alerts and audit rows carry no
  content; only age *band* is kept, never the birth date.
- **Retention**: `expires_at` is set at case creation, shown in the UI,
  filtered in every query, and enforced by the cleanup job (startup + daily).
- **Keys** (`signing.key`, `fernet.key`) are generated on first run inside the
  gitignored `backend/data/` directory.
- **Prototype boundary**: local HTTP on trusted Wi-Fi, synthetic data only.
  A real deployment would need HTTPS, secret management, hardened hosting, and
  independent review (roadmap §16.4) — all explicitly out of scope for v0.1.

## 7. Testing strategy

- `backend/tests/` (pytest + FastAPI TestClient, fresh temp data dir per test):
  auth/age gate, link codes, IDOR and cross-org isolation, encryption-at-rest,
  retention, alert rules and dedupe, report scoping, PDF masking, OCR
  validation, privacy export/delete.
- `tests/fixtures/labeled_samples.jsonl`: shared labeled examples asserted
  against the classifier (labels, Body Shaming tags, determinism, obfuscation).
- Mobile: strict TypeScript (`npx tsc --noEmit`) and bundle verification
  (`npx expo export`). Physical-device flows follow the roadmap §18.1 manual
  checklist.

## 8. Day-to-day workflow

```bash
# after changing backend code
conda activate a-mbl && python -m pytest backend/tests

# after changing mobile code
cd mobile && npx tsc --noEmit          # phones hot-reload via `npx expo start`

# reset all local data (database, keys, evidence)
rm -rf backend/data && python -m backend.scripts.seed_demo
```

Contract discipline: change `backend/app/schemas.py` → update
`mobile/src/lib/types.ts` to match → add/adjust a test. FastAPI's live OpenAPI
document at `/docs` is the reference if the two ever disagree.

## 9. Extension points (in roadmap order)

1. **Trained model** (weeks 3–4): dataset prep in `ml/`, TF-IDF + calibrated
   Logistic Regression, swap into `classifier.classify()` behind the same
   `Prediction` interface, register a new `model_versions` row. Nothing else
   changes. Gates: accuracy ≥ 85 %, FPR < 10 %, macro-F1 ≥ 0.75, threat recall
   ≥ 0.80 — reported honestly either way.
2. **OCR hardening**: OpenCV preprocessing variants, rotation correction,
   fixture suite (§13).
3. **In-app PDF download**: add `expo-file-system` + `expo-sharing` and wire
   the existing `POST /v1/reports/pdf`.
4. **Generated API types**: replace the hand-mirrored `types.ts` with
   OpenAPI-generated types once the contract stabilizes.
