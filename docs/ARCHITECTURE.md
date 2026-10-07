# a-mbl architecture and workflow

How the system fits together, how a request flows through it, and how to work
on it day to day. The product spec is [MOBILE_APP_ROADMAP.md](MOBILE_APP_ROADMAP.md);
deviations and their reasons are in [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md);
run instructions are in [HOW_TO_RUN.md](HOW_TO_RUN.md).

## 1. System overview

```text
┌─────────────────────────────┐  same Wi-Fi, or an https  ┌──────────────────────────────────┐
│  Phone (Expo Go or APK)     │  tunnel for remote tests  │  Mac                             │
│                             │ ───────────────────────►  │                                  │
│  mobile/ — Expo Router app  │                           │  backend/ — FastAPI (uvicorn)    │
│  · SecureStore: refresh     │  ◄───────────────────────  │  · auth / roles / scoping        │
│    token + server address   │        /v1 responses      │  · hybrid classifier + policy    │
│  · access token in memory   │                           │  · OCR (Tesseract, optional)     │
│  · no analyzed content      │                           │  · reports (ReportLab PDF)       │
│    persisted on device      │                           │  · retention cleanup (24 h)      │
│                             │                           │  · email alerts (SMTP, optional) │
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
Alerts tab gains focus. The only outbound channel is optional: when the
`A_MBL_SMTP_*` variables are set, non-owner alert recipients also get a
content-free email (`emailer.py`).

The backend also runs on Windows (`backend/run.ps1`, the PowerShell
counterpart of `run.sh`; see [HOW_TO_RUN.md](HOW_TO_RUN.md) §2).

The app reaches the backend in one of two ways: `http://<mac-ip>:8000` on the
same Wi-Fi (Expo Go during development, or the APK, which allows cleartext
HTTP for this reason), or a temporary `https://…trycloudflare.com` quick
tunnel for remote testers ([DEVICE_TESTING.md](DEVICE_TESTING.md)).

## 2. Backend layout (`backend/app/`)

| Module | Responsibility |
| --- | --- |
| `main.py` | App factory, CORS, router registration, lifespan (model version registration + retention cleanup at startup and every 24 h; a failed run is logged and retried, never ends the loop) |
| `config.py` | All tunables: token lifetimes, 30-day retention, size limits, 0.70/0.80 confidence thresholds, data directory |
| `db.py` | SQLite schema (14 tables), per-request connection dependency (commit on success, rollback on error), id/time helpers, audit writer |
| `security.py` | PBKDF2 password hashing, HMAC-signed 15-min access tokens, rotating 7-day refresh tokens (stored as SHA-256 hashes), Fernet encryption for case text/notes/evidence |
| `classifier.py` + `lexicon.py` | Hybrid classifier. At import it loads `ml/artifacts/model.joblib` if present (`A_MBL_MODEL_PATH` overrides the path; `A_MBL_FORCE_LEXICON=1` skips loading): the trained TF-IDF + logistic-regression pipeline (version from the artifact, e.g. `tfidf-logreg-0.2.0`) picks label and confidence with per-class thresholds checked worst class first, then merges severity-max with the lexicon (the more severe label wins; on a tie the higher confidence). The deterministic `lexicon-0.1.0` baseline — normalization (lowercase, leet-speak, repeat-collapse), word-boundary phrase matching per category, heuristic confidence (+0.10 when a match only appears after de-obfuscation) — always supplies the matched terms for masking and the Body Shaming tag, and is the whole classifier when the artifact is missing or fails to load. `/v1/health.modelVersion` and the `model_versions` row name whichever is active |
| `emailer.py` | Optional SMTP alert emails (FR5), configured by `A_MBL_SMTP_HOST`/`_FROM` (required), `_PORT` (587), `_USER`, `_PASSWORD`, `_STARTTLS` (1); sent on a daemon thread, failures logged, never any message content |
| `policy.py` | Severity mapping (§6.2), Body Shaming floor to High, `needsReview` < 0.70, alert eligibility, cautious advice strings |
| `deps.py` | `current_user` / `active_user` auth dependencies and `case_scope()` — the single SQL fragment that enforces the §5.4 permission matrix on every case query |
| `errors.py` | The uniform `{code, message, fieldErrors?, requestId}` error body for every non-success response |
| `ocr.py` | Magic-byte + Pillow validation, then Tesseract if installed (`/v1/health.ocrReady` feature flag); finds `tesseract` on `PATH` or in the Windows installer's default folders |
| `pdf.py` | In-memory masked PDF (no temp files) |
| `retention.py` | Expired-case deletion (files first, then rows), stale code/token purge |
| `routers/` | One file per API area: `health`, `auth`, `links`, `analysis`, `cases`, `alerts`, `reports`, `privacy` |

`backend/scripts/`: `create_admin.py` (invitation-only school-admin accounts),
`seed_demo.py` (synthetic demo data). `backend/run.sh` / `backend/run.ps1`
start uvicorn on `0.0.0.0:8000` and print the LAN addresses (macOS / Windows).

`ml/train.py` (outside the backend) builds `ml/artifacts/model.joblib` from
the Jigsaw Toxic Comment `train.csv` in `ml/data/`; both folders are
gitignored. On the development Mac both exist, so the backend there runs the
hybrid (`tfidf-logreg-0.2.0`); a fresh clone runs the lexicon alone. See
[ml/README.md](../ml/README.md).

## 3. Mobile layout (`mobile/src/`)

| Path | Responsibility |
| --- | --- |
| `lib/api.ts` | Typed fetch wrapper: base URL + refresh token in SecureStore, access token in memory, single-flight refresh with one retry on 401, uniform `ApiError`, server-address normalization (`normalizeServerUrl`) |
| `lib/auth.tsx` | `AuthProvider`: restores the session from the refresh token at boot, exposes `signIn/register/signOut/reloadUser` |
| `lib/types.ts` | Hand-mirrored API contract types (source of truth: FastAPI's `/docs`) |
| `lib/theme.ts` | Pastel palette, severity metadata (icon + label + colors — never color alone), date/percent formatters |
| `components/ui.tsx` | Screen/Card/Button/Field/Banner/SeverityChip/etc. — 48pt touch targets, accessibility labels; `Screen` keeps focused fields above the keyboard (Android: padding by the keyboard overlap; iOS: `automaticallyAdjustKeyboardInsets`) and adds the status-bar inset only on header-less screens (`safeTop`) |
| `components/charts.tsx` | `ColumnChart` and `BarRows`: plain `View`-based bar charts for the Home dashboard (no chart library), one theme colour, values as direct labels, an accessibility label per bar |
| `app/index.tsx` | Boot router: no server → `/connect`; no session → welcome; pending → `/pending`; else tabs |
| `app/connect.tsx` | Editable server address (accepts `host:port` without a scheme, or a pasted `/v1/health` link) + `/v1/health` check that confirms an a-mbl server answered, with troubleshooting hints |
| `app/(auth)/` | `welcome` → `age` (neutral month/year gate, under-13 stops with nothing saved) → `register` / `login` |
| `app/pending.tsx` | 13–17 waiting room: shows/regenerates the one-time guardian code, re-checks status |
| `app/(tabs)/` | `index` (role-scoped 30-day summary plus charts from the same `/v1/reports/summary` call: cases per week, by day of week (`byWeekday`), repeat senders (`topSenders`)), `analyze` (text + screenshot→OCR→correct→analyze), `cases` (filterable list), `alerts` (content-free inbox), `profile` (links, privacy, sign-out) |
| `app/case/[id].tsx` | Case detail: deliberate **Reveal**, human reviews, named-confirmation org sharing, encrypted evidence attach/view, delete |
| `app/reports.tsx`, `app/members.tsx` | Date-ranged summaries, weekly trend, alias grouping, masked PDF download/share; school-admin member management |
| `lib/images.ts` | Screenshot normalization before upload (JPEG re-encode, EXIF stripped, longest edge ≤ 2000 px) the multipart body for `/v1/ocr` and evidence (an `expo-file-system` `File` part, because Expo's global `fetch`, `expo/fetch`, rejects React Native `{uri, name, type}` parts), and `imageDataUri` for showing downloaded evidence from memory (Android's `<Image>` does not send request headers) |
| `app.json`, `scripts/build-apk.sh` | Expo config (Android package `com.ambl.app`, icons, splash, permissions text, cleartext HTTP for the APK); one-command release APK build |
| `scripts/check-casing.mjs` | Resolves every local import under `src/` case-sensitively, so an import whose case differs from the file name (which Windows tolerates) fails locally; `npm run check:casing`, or `npm run check` for casing + `tsc --noEmit` |

## 4. Key flows

### Text analysis (§7.2)

```text
Analyze tab ──POST /v1/analyses {text, sourceType, platformName?, senderAlias?}──►
  classifier.classify(text)  →  label, confidence, bodyShaming, matched terms
                                (model + lexicon, severity-max; lexicon alone without model.joblib)
  policy: severity, needsReview(<0.70), advice
  INSERT analysis_events      (metadata only — never the text)
  severity != safe?
    ├─ yes → INSERT flagged_cases (Fernet-encrypted text, expires +30 days)
    │        alert-eligible (harassment/hate/threat, High/Critical, conf ≥ 0.80)?
    │          └─ yes → INSERT OR IGNORE alerts for owner + actively linked guardians
    │                   newly inserted non-owner rows + SMTP configured → content-free email
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
    + one email per newly inserted admin alert row when SMTP is configured
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
  previews computed on demand, never stored, and replaced by "Content
  withheld — open the case to view it." when a non-normal verdict has no
  literal matched term to mask (possible only with the trained model);
  alerts, alert emails and audit rows carry no content; only age *band* is
  kept, never the birth date.
- **Retention**: `expires_at` is set at case creation, shown in the UI,
  filtered in every query, and enforced by the cleanup job (startup + daily).
- **Keys** (`signing.key`, `fernet.key`) are generated on first run inside the
  gitignored `backend/data/` directory.
- **Prototype boundary**: local HTTP on trusted Wi-Fi, synthetic data only.
  A real deployment would need HTTPS, secret management, hardened hosting, and
  independent review (roadmap §16.4) — all explicitly out of scope for version 0.2.0.

## 7. Testing strategy

- `backend/tests/` (pytest + FastAPI TestClient, fresh temp data dir per test):
  auth/age gate, link codes, IDOR and cross-org isolation, encryption-at-rest,
  retention, alert rules and dedupe, email alerts (delivery captured in
  memory, never a real SMTP connection; no content; no re-send on a repeated
  share), report scoping (including `byWeekday` and `topSenders`), PDF
  masking, OCR validation, privacy export/delete. `conftest.py` sets
  `A_MBL_FORCE_LEXICON=1` and clears every `A_MBL_SMTP_*` variable, so the
  suite asserts the lexicon's exact outputs whether or not `model.joblib`
  exists. 120 tests.
- `tests/fixtures/labeled_samples.jsonl`: shared labeled examples asserted
  against the classifier (labels, Body Shaming tags, determinism, obfuscation);
  `test_classifier.py` also checks that an obfuscated spelling (`l0ser`)
  scores higher than the plain one and clears the needs-review threshold.
- The trained model's own evaluation (held-out test split, four gates) is
  produced by `ml/train.py`, not by the pytest suite; the results measured on
  the development Mac are in [ml/README.md](../ml/README.md).
- Mobile: import-casing check + strict TypeScript (`npm run check`, i.e.
  `scripts/check-casing.mjs` then `tsc --noEmit`), ESLint (`npm run lint`),
  `npx expo-doctor`, and bundle verification (`npx expo export`). The release
  APK is smoke-tested on an Android emulator against a live backend
  (`http://10.0.2.2:8000`) before it is sent out. Physical-device flows follow
  the roadmap §18.1 manual checklist.

## 8. Day-to-day workflow

```bash
# after changing backend code
conda activate a-mbl && python -m pytest backend/tests

# after changing mobile code
cd mobile && npm run check && npm run lint   # casing + tsc, then ESLint; phones hot-reload via `npx expo start`

# train (or retrain) the classifier; needs ml/data/train.csv (see ml/README.md)
pip install -r ml/requirements.txt && python ml/train.py   # then restart the backend

# a new installable Android build for testers
cd mobile && npm run build:apk         # → dist/a-mbl-<version>.apk

# reset all local data (database, keys, evidence)
rm -rf backend/data && python -m backend.scripts.seed_demo
```

Contract discipline: change `backend/app/schemas.py` → update
`mobile/src/lib/types.ts` to match → add/adjust a test. FastAPI's live OpenAPI
document at `/docs` is the reference if the two ever disagree.

## 9. Extension points (in roadmap order)

1. **Stronger model**: a fine-tuned transformer compared against the TF-IDF
   baseline, and a labeled body-shaming dataset so the tag can move off the
   lexicon (ml/README.md "Future work"). It would plug in the same way the
   TF-IDF model did: behind `classifier.classify()` and the `Prediction`
   interface, with its own `model_versions` row.
2. **OCR on OpenCV**: the Pillow preprocessing variants (grayscale,
   autocontrast, inversion, binarization) and 90/180/270° rotation retry are
   done; OpenCV skew correction remains the roadmap's (§13) optional next step.
3. **Generated API types**: replace the hand-mirrored `types.ts` with
   OpenAPI-generated types once the contract stabilizes.

(In-app PDF download/share — once listed here — shipped on 2026-07-12 via
`expo-file-system` + `expo-sharing` on the Reports screen. The trained model —
also once listed here — is integrated as the hybrid classifier in §2 behind
the same `Prediction` interface. Trained on the development Mac, its gate
results (ml/README.md) are accuracy 0.903 and FPR 0.053, both met, and threat
recall 0.718 and macro-F1 0.558, both missed (targets 0.80 and 0.75).
`model.joblib` is not in Git, so other machines copy it in or retrain.)
