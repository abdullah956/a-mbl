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
  screen with editable server address and health check (a development-only
  `EXPO_PUBLIC_API_URL` pre-fills it, roadmap §9.3), neutral age screen,
  register/login, pending-approval screen with link code, five tabs
  (Home/Analyze/Cases/Alerts/Profile), text analysis with inline result,
  screenshot → OCR → correct → analyze flow (shown only once the server
  confirms OCR is available), case detail with deliberate **Reveal**, human reviews,
  organization sharing with named confirmation, evidence attach/view,
  guardian linking, data export, account deletion.
- **Tests**: 115 pytest cases (`backend/tests/`) covering auth (including
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
`http://192.168.1.20:8000`). For an installable Android build,
`npm run build:apk` writes `dist/a-mbl-0.1.0.apk` (see
[DEVICE_TESTING.md](DEVICE_TESTING.md) §2).

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
| ~~PDF download inside the app (§15.2)~~ resolved 2026-07-12 | The Reports screen downloads and shares the masked PDF via `expo-file-system` + `expo-sharing` | Formerly deferred; the packages the roadmap prescribed are now installed and wired.                                                             |
| Tesseract OCR always on (§13)                    | Feature flag:`/v1/health.ocrReady`; the app shows the scan flow only after the server confirms it is ready | Tesseract is a system binary that may not be installed (`conda install -n a-mbl -c conda-forge tesseract`). Upload validation still runs and is tested either way.     |
| Jest + React Native Testing Library (§9.1, §18.1) | No mobile test runner yet; the gates are strict TypeScript (`npx tsc --noEmit`), `expo export`, and the backend suite | The screens are thin wrappers over the API, which the 115 pytest cases exercise; a Jest/RNTL harness is still planned before the trained-model work. |

## Feature completions on 2026-07-12

Closed every remaining roadmap gap that does not require the trained model:

- **Reports screen** (`mobile/src/app/reports.tsx`, §15.1/§8.1/§8.4): date-range
  presets + custom range, accessible weekly-trend chart, category/severity
  breakdowns, unverified sender-alias grouping (new `bySender` in
  `GET /v1/reports/summary`), and masked-PDF download/share on the phone.
- **PDF review notes** (§15.2): the PDF now includes human review notes for the
  cases the requester's role scope grants, escaped against markup.
- **Member management** (§8.4): new `POST /v1/organizations/{id}/members`
  (existing school-admin accounts only) plus a Members screen
  (`mobile/src/app/members.tsx`) reachable from Home/Profile for admins.
  Memberships carry a `status` column (§11) that is *enforced*, not just
  displayed: a non-active membership grants no case access (`deps.case_scope`),
  no member management, no organization listing, and no alerts.
- **Guardian link preview** (§7.1 step 7): new `POST /v1/guardian-links/preview`
  shows who a code belongs to before the guardian approves; the profile screen
  now reviews-then-approves.
- **Manual flagging** (§6.3): `flagForReview` on `POST /v1/analyses` keeps ANY
  result — including Normal — as a review-requested case with the submitter's
  consent (the one deliberate exception to "normal text is never stored");
  flagged-safe results never alert. The result card offers it for safe results
  and states plainly that keeping the message stores it for 30 days and lets
  anyone already scoped to the user's cases (a linked guardian) open it.
- **Request review / case context** (§7.4): `PATCH /v1/cases/{id}` accepts
  `requestReview`; adding a review clears it; the case screen has a
  Context-and-review card for owners (edit platform/sender, request review).
- **OCR hardening** (§13, Pillow-based rather than OpenCV): preprocessing
  variants (grayscale, autocontrast, inversion for dark mode, binarization)
  with best-confidence selection and 90/180/270° rotation retry; covered by new
  dark-mode / low-contrast / rotated / empty-image tests.
- **Client-side image normalization** (§7.3): every upload is re-encoded to
  JPEG (EXIF stripped, orientation baked) and capped at 2000 px via
  `expo-image-manipulator`; when the picker does not report dimensions, the
  image is measured rather than assumed small.
- **Alerts refresh** (§14.2): foreground (AppState) refresh and a 60 s poll
  while the inbox is open, alongside the existing focus/pull-to-refresh.
- **Profile editing and permissions** (§10.1): display name editable in the app
  (PATCH /v1/me), and `GET /v1/me` now returns a `permissions` object alongside
  the profile. It is advisory — the SQL scope in `deps.case_scope` remains the
  only real access control.
- **Masking of manually flagged Normal text** (§15.2): a Normal message has no
  flagged terms, so term-censoring left it verbatim in previews and the PDF.
  `classifier.mask_text` now censors every word when there is nothing specific
  to censor, so a preview can never leak a raw message.
- **Privacy** (§7.5): account deletion now de-identifies earlier audit rows —
  the deleted account's id is nulled both where it acted (`actor_id`) and where
  it was acted upon (`object_id`) — so only aggregate counters remain.
- **Error contract** (§10.5): malformed JSON bodies return 400 `bad_request`
  (well-formed bodies with bad values remain 422).
- **Accessibility** (§8.5): dynamic-type caps (`maxFontSizeMultiplier`) across
  the UI kit so enlarged text reflows instead of clipping; the weekly chart has
  a spoken summary label.
- **Docs**: role flows and error states recorded in [FLOWS.md](FLOWS.md);
  benign identity/slang fixture slices added (the lexicon flags all profanity
  as at least Offensive, so a benign-profanity slice only becomes meaningful
  with the §12 trained model).
- **Schema**: `flagged_cases.review_requested`,
  `organization_memberships.status`, and the §11 `model_versions` columns
  (`artifact_checksum`, `label_map_json`, `metrics_json` — NULL until a trained
  model exists) added via idempotent ALTERs at connect time; existing dev
  databases migrate automatically, no reset needed.

### What remains open

Blocked on multi-week dataset/model work (a fake trained model would violate
the §18.5 honesty rules): the §12 trained TF-IDF model, its §12.3 evaluation
gates / metrics / model card, and the §18.4 recorded device-latency runs that
§17 says must use the final artifacts.

Separately, the accepted substitutions in the deviations table above are still
roadmap deltas, not completed requirements — role-specific tab sets (§8.2–8.4),
Argon2 (§16.3), SQLAlchemy + Alembic (§9.2), TanStack Query / RHF / Zod (§9.1),
OpenAPI-generated TS types (§10), OpenCV OCR preprocessing (§13), and mobile
Jest/RNTL tests (§18.1). They are deliberate, documented, and reversible; they
are not "done".

## Fixes on 2026-07-12

- **PDF crash**: `POST /v1/reports/pdf` returned 500 whenever a display name
  or masked case text contained markup-like characters (`<b>`, `&`) —
  ReportLab's `Paragraph` parses mini-XML. User-derived strings are now
  escaped in `backend/app/pdf.py`, with a regression test.
- **Refresh race**: the mobile app had two independent refresh paths (boot and
  evidence reload bypassed the single-flight one). Because the backend treats
  refresh-token reuse as theft and revokes every session, concurrent refreshes
  could sign the user out everywhere. All callers now share one single-flight
  `refreshSession()` in `mobile/src/lib/api.ts`, and the stored token is only
  cleared when the server answers 401 (not on transient errors).
- **OCR gating**: the screenshot scan buttons appeared even when the health
  check had failed; the scan flow now shows only after the server positively
  confirms `ocrReady`, with distinct messages for "not installed" vs
  "could not check".
- **Demo seed**: `seed_demo.py` produced no caution-severity case; it now
  seeds one of each case severity (caution, high, critical) as
  `HOW_TO_RUN.md` describes.
- **`EXPO_PUBLIC_API_URL`** (§9.3): now implemented as a development-only
  default that pre-fills the connection screen and seeds the API base URL
  until an address is saved in the app.

## Fixes on 2026-09-10

From the full code review recorded in [PROJECT_GUIDE.md](../PROJECT_GUIDE.md) §19:

- **Classifier gap (safety)**: leet spelling plus word-final punctuation read as
  Normal (`i will k1ll you!` → normal, discarded, no alert) because the leet
  map turned the final `!` into `i`. `variants()` now also searches a leet
  form with word-final `!@$` dropped first. New fixtures + regression test.
- **Masked previews (§15.2)**: only the matched harmful words were censored,
  so the rest of the first 80 characters (names, places, times) stayed
  readable in case previews and the PDF. `mask_text` now reduces every word to
  its first letter; the full text is still available behind **Reveal** to
  authorized viewers.
- **Mobile 401 handling**: `api()` refreshed the session on *every* 401,
  including a wrong password on account deletion (`invalid_credentials`),
  rotating the refresh token for nothing. It now refreshes only on
  `unauthorized`.
- **Keys**: `signing.key` / `fernet.key` are created at startup with an
  exclusive create, so concurrent first requests can never write two
  different keys.
- **Audit of failed cleanup**: a failed evidence unlink during case or account
  deletion now commits its `evidence_cleanup_failed` audit row before the 503
  (it used to be rolled back).
- **Smaller fixes**: `share_case` uses `policy.alert_eligible` instead of a
  hand copy; alert-cleanup SQL ignores suspended memberships; alerts show the
  owner's current display name; the rate limiter sweeps idle keys; the schema
  script runs once per database file instead of on every request; the Home
  tab refreshes on focus; case/reports/members screens redirect when signed
  out; `create_admin` uses `config.MIN_PASSWORD_CHARS`; `seed_demo` keeps the
  teen 13–17 relative to today and no longer duplicates samples on re-run.
- **Cleanup**: removed the unused `expo-web-browser`, `expo-device`,
  `expo-image` packages and the unused Expo template images. (`@expo/ui`,
  `expo-glass-effect`, `expo-symbols` stay — expo-router depends on them.)

Left as deliberate choices: adults may create guardian link codes (§5.1 lets
any User create a link; it is consent-based), login throttling stays per email
(local demo), and "keep for human review" records a second analysis event
because the first one's text was already discarded.

## Changes on 2026-10-05

- **Installable Android APK**: `mobile/scripts/build-apk.sh` (`npm run
  build:apk`) regenerates `android/` with `expo prebuild` and builds a
  standalone release APK (arm64-v8a + armeabi-v7a) into `dist/` at the
  repository root, signed with the standard React Native debug keystore for
  sideloading. `app.json` gained the Android package id `com.ambl.app`, a
  `versionCode`, and `expo-build-properties` with `usesCleartextTraffic` so
  the APK can reach `http://<mac-ip>:8000` on a LAN (release builds block
  cleartext HTTP by default). The APK was installed on an Android 15 emulator
  and driven end to end against a live backend before being shared.
  [DEVICE_TESTING.md](DEVICE_TESTING.md) §2 covers building, sending, and
  running a remote session through a Cloudflare quick tunnel.
- **App identity**: the Expo template icons (blue "A", Expo symbol) were
  replaced with an a-mbl icon set (speech bubble + shield on the app purple:
  icon, adaptive foreground/background/monochrome layers, splash, favicon),
  and the template's iOS Icon Composer bundle (`assets/expo.icon`) and MIT
  `LICENSE` (© 650 Industries) were removed.
- **Expo SDK 57 patch upgrade**: `expo` 57.0.4 → 57.0.26 and every Expo
  package aligned (`react-native` 0.86.3), fixing the Hermes V1 memory
  regression that `expo-doctor` flagged for 57.0.4; `expo-doctor` now passes
  21/21 checks.
- **ESLint**: `npm run lint` now runs `eslint-config-expo` (flat config in
  `mobile/eslint.config.js`) instead of prompting to set ESLint up.
- **Server address entry**: the connect screen accepts `192.168.1.20:8000`
  without a scheme and strips a pasted `/v1/health`, `/v1` or `/docs` suffix
  (`normalizeServerUrl` in `lib/api.ts`), and the health check only accepts a
  response that really is an a-mbl server. The wording no longer assumes the
  phone is next to the Mac, since remote testers use an https link. Profile
  shows the app version and the current server.
- **Screenshot uploads were broken (found on the emulator)**: Expo SDK 57
  installs `expo/fetch` as the global `fetch`, and its FormData encoder
  rejects React Native's `{ uri, name, type }` file parts before the request
  is sent. Both "Scan screenshot" (`/v1/ocr`) and "Attach screenshot"
  (`/v1/cases/{id}/evidence`) failed with a misleading "could not reach the
  server" message. Uploads are now built by `screenshotFormData()` in
  `lib/images.ts`, which appends an `expo-file-system` `File` (a Blob that
  `expo/fetch` reads as bytes). A timed-out request now says so instead of
  claiming the server is unreachable.
- **Viewing attached screenshots was broken on Android (found on the
  emulator)**: the case screen loaded evidence through `<Image source={{uri,
  headers}}>`, but Android's image loader does not send those headers, so
  every view answered 401 and showed "could not be loaded". The image is now
  downloaded through the API client (`apiBinary`, which also refreshes an
  expired session) and shown from memory as a data URI (`imageDataUri` in
  `lib/images.ts`); the decrypted screenshot is never written to the
  phone's storage.
- **Layout under navigation headers**: the shared `Screen` added the
  status-bar inset on top of the header, leaving an empty band above every
  titled screen. Only header-less screens (welcome, boot) take the top inset
  now (`safeTop`).
- **Keyboard covering fields on Android**: edge-to-edge Android no longer
  resizes the window for the keyboard, so a focused field low on the screen
  (password, sender nickname, link code, review note) sat under the keyboard.
  `Screen` now pads by the keyboard overlap on Android (measured against the
  screen's position below the header) so the focused field scrolls into
  view; iOS uses `automaticallyAdjustKeyboardInsets`.
- **List order**: cases, alerts, PDF rows and reviews created in the same
  second (timestamps have one-second resolution) came back in arbitrary
  order; `rowid` is now the tie-breaker (new regression test).
- **Lint-driven fixes**: case detail, reports and members load through
  `useFocusEffect` like the tab screens (so they also refresh when you come
  back to them) instead of setting state from `useEffect`; JSX apostrophes
  are typographic.
- **Wording**: the teen's waiting screen pointed guardians to "Profile →
  Guardian links", but the guardian's section is called "Linked users".
- **Retention loop**: an exception in the 24-hour cleanup used to end the
  background task for good, silently stopping retention until a restart. It
  is now logged and retried at the next interval (new regression test).
- **Consistent timestamps**: adding a review, attaching evidence, and sharing
  a case now return the same timestamp they store, instead of a second
  `now_iso()` call.
- **Test client dependency**: Starlette 1.3 (with current FastAPI) runs its
  `TestClient` on the `httpx2` package and warned that `httpx` is
  deprecated, so `backend/requirements.txt` now lists `httpx2`; the suite
  runs warning-free.
- **OCR on by default on this Mac**: Tesseract 5.5 is installed into the
  `a-mbl` conda env from conda-forge, so `/v1/health` reports
  `ocrReady: true` and the real OCR tests (dark mode, low contrast, rotation)
  run instead of the "not installed" path.
- **Docs**: new non-technical [CLIENT_GUIDE.md](../CLIENT_GUIDE.md) with
  diagrams, emulator screenshots, and a test script; the technical
  [PROJECT_GUIDE.md](../PROJECT_GUIDE.md) is now tracked in Git; every doc
  updated for the APK route, conda-based tools, and the 115-test suite.

## Known limitations

- The lexicon classifier misses anything outside its word lists and has no
  measured accuracy; treat every result as the uncertain estimate the UI says
  it is.
- Local HTTP on a shared Wi-Fi network, or a temporary public quick tunnel for
  remote testers; synthetic content only (§16.4).
- In-app alerts refresh on tab focus, on returning to the foreground, via a
  60-second poll while the inbox is open, and on pull-to-refresh; there are
  no push notifications by design (§4.2).
- Evidence is downloaded on demand through the API client and held in memory
  while the case is open; very large screenshots take a moment to appear (the
  upload side caps them at 2000 px).
