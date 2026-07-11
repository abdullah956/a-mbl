# a-mbl Mobile Application Roadmap

## 1. Purpose

`a-mbl` will be a mobile-first cyberbullying review tool for content that a user deliberately submits. It will accept typed or pasted English text and screenshots selected from the device camera or gallery. A local AI service will classify the confirmed text, explain the risk level in cautious language, and create a reviewable case when the content appears harmful.

The application is intended to support early awareness and human decision-making. It must not present a model prediction as proof that cyberbullying occurred, identify an alleged offender automatically, or take action outside the application without a user-authorized workflow.

This document is the implementation plan for a local, end-to-end prototype. It defines what version one will do, what it will not do, and the order in which it should be built.

## 2. Locked version-one decisions

| Decision | Version-one choice |
| --- | --- |
| Mobile framework | Expo React Native with TypeScript |
| Mobile platforms | Android and iPhone through Expo Go |
| Backend | FastAPI running locally on the Mac |
| Python environment | Conda environment named `a-mbl` using Python 3.11 |
| Database | SQLite |
| Evidence storage | Encrypted files stored locally on the Mac |
| Input methods | Manual text entry and one screenshot at a time |
| Analysis language | English |
| Primary categories | Normal, Offensive, Harassment, Hate Speech, Threat |
| Secondary signal | Body Shaming tag |
| Roles | User, Guardian, School Administrator |
| Alerts | Risk-tiered in-app alert inbox |
| Reports | In-app summaries and masked PDF export |
| Evidence retention | 30 days by default |
| Distribution | Local Expo Go demonstration; no store publication |

## 3. Product goals and success criteria

### 3.1 Goals

1. Make text and screenshot analysis understandable to non-technical users.
2. Keep the user in control of what is submitted, saved, linked, and shared.
3. Separate AI predictions from human review decisions.
4. Apply consistent access rules for Users, Guardians, and School Administrators.
5. Minimize how much sensitive content is retained.
6. Produce a repeatable local prototype that works on both Android and iPhone.

### 3.2 Prototype success criteria

The prototype will be considered functionally complete when:

- A physical Android device and a physical iPhone can open the app through Expo Go and reach the FastAPI service on the same Wi-Fi network.
- A user can register, sign in, submit text, and receive a structured classification result.
- A user can select a screenshot, review and correct OCR text, and then analyze the corrected text.
- All five primary classes and the Body Shaming tag are represented in the API and interface.
- Guardian and School Administrator views enforce the access rules defined in this document.
- High-risk cases create scoped in-app alerts without exposing raw content in the alert preview.
- Normal raw input is not retained, while harmful cases expire after 30 days.
- A masked PDF report can be generated for the cases visible to the requesting role.
- Automated tests cover the critical API, model, retention, and permission rules.
- Actual model and performance measurements are documented without inflating the results.

## 4. Scope boundaries

### 4.1 Included

- Email-and-password authentication for local prototype accounts.
- A neutral age screen before account details are collected.
- Accounts for users aged 13 and above.
- Guardian approval and linking for users aged 13–17.
- Invitation-only School Administrator accounts.
- Manual English text analysis up to 5,000 characters.
- One JPEG or PNG screenshot per OCR request, up to 10 MB.
- OCR review and correction before classification.
- Classification, confidence, severity, uncertainty, and safe next-step guidance.
- Optional user-entered platform name and sender alias for report grouping.
- Harmful-case history, review notes, in-app alerts, and explicit organization sharing.
- Data export and deletion controls.
- Mobile summaries and masked PDF reports.

### 4.2 Explicitly excluded

- Background monitoring or reading content from other applications.
- Custom keyboards, share extensions, accessibility-service monitoring, or notification interception.
- Direct integrations with social-media or messaging platforms.
- Automatic collection of sender identity, platform identity, or conversation history.
- Arabic or multilingual analysis.
- Audio, video, sticker, emoji-only, or general image-content moderation.
- Automatic disciplinary action or reporting to a school, authority, emergency service, or third party.
- Remote push notifications, SMS, and email alerts.
- A web dashboard or a second administrator application.
- Cloud hosting, Docker infrastructure, public deployment, App Store submission, and Google Play submission.
- Under-13 accounts.
- Claims of production readiness, guaranteed accuracy, or legal compliance.

## 5. Users, roles, and authorization

### 5.1 User

A User submits and manages their own content. Users can:

- Analyze text and screenshots.
- See their own results and harmful cases.
- Correct OCR output before analysis.
- Add a review note or human-corrected category without overwriting the original model output.
- Create or revoke a Guardian link.
- Explicitly share or unshare a selected case with an organization.
- Generate a report containing only their visible cases.
- Export or delete their data.

Users aged 13–17 remain in a pending state until a Guardian approves the link. Users aged 18 or above can activate directly. The age screen should request month and year neutrally and should not encourage a particular answer.

### 5.2 Guardian

A Guardian can:

- Analyze their own submitted content.
- Approve a one-time Guardian link code that expires after 24 hours.
- View cases belonging to linked users aged 13–17.
- Receive scoped in-app alerts for eligible linked-user cases.
- Add review notes and a separate human-reviewed category.
- Generate reports limited to their own and linked-user cases.
- Revoke a link without deleting the other account.

A Guardian link must never grant access to unrelated users or organization-wide data.

### 5.3 School Administrator

A School Administrator account is created through a local backend command and assigned to one organization. Administrators can:

- Analyze their own submitted content.
- View only cases explicitly shared with their organization.
- Add review notes and a human-reviewed category to shared cases.
- Receive in-app alerts only for eligible shared cases.
- Generate organization reports containing shared cases only.
- Manage memberships inside their own organization.

The public registration endpoint must not accept `school_admin` as a selectable role.

### 5.4 Permission matrix

| Capability | User | Guardian | School Administrator |
| --- | ---: | ---: | ---: |
| Analyze own content | Yes | Yes | Yes |
| View own cases | Yes | Yes | Yes |
| View linked user's cases | No | Yes | No |
| View organization cases | No | No | Explicitly shared only |
| Add human review | Own cases | Linked cases | Shared cases |
| Receive scoped alerts | Own results | Linked users | Shared cases |
| Generate reports | Own scope | Own and linked scope | Organization-shared scope |
| Delete own account | Yes | Yes | Yes |
| Manage organization members | No | No | Own organization only |

Every backend query must apply these rules. Hiding a screen in the mobile client is not an authorization control.

## 6. Classification and risk policy

### 6.1 Primary categories

| Category | Product meaning |
| --- | --- |
| Normal | No clear harmful-language signal detected in the submitted text. |
| Offensive | Profanity, insults, or inappropriate wording without a stronger supported category. |
| Harassment | Targeted abusive or degrading language. A single submitted message cannot prove repeated behavior. |
| Hate Speech | Harmful language targeting a protected identity or group. |
| Threat | Language that appears to express or encourage direct harm. |

Body Shaming is a separate Boolean tag because it can overlap with Offensive or Harassment content. It is not a sixth mutually exclusive primary category.

### 6.2 Severity mapping

| Result | Severity |
| --- | --- |
| Normal | Safe |
| Offensive | Caution |
| Harassment | High |
| Hate Speech | High |
| Threat | Critical |
| Any Body Shaming tag | At least High |

### 6.3 Confidence and review behavior

- A calibrated confidence below `0.70` sets `needsReview` to `true` and displays an uncertain-result message.
- A High or Critical result with confidence of at least `0.80` is eligible for a linked-role in-app alert.
- Offensive results create a harmful case but do not alert a Guardian or School Administrator.
- A user may manually flag any result for review regardless of model confidence.
- Thresholds must be stored with the model version and may be adjusted only after validation; changes require updated test evidence.
- The original model result is immutable. Human corrections are stored separately with reviewer, time, and note.

## 7. Core user journeys

### 7.1 Registration and linking

1. The app checks that the local API is reachable.
2. The user enters birth month and year before other personal details.
3. Under-13 registration stops without creating an account.
4. The user selects User or Guardian; School Administrator is unavailable.
5. The account is created with email and password.
6. A 13–17 User receives a one-time link code and remains pending.
7. A Guardian signs in, enters the code, reviews the link, and approves it.
8. The User account becomes active and the link is recorded in the audit history.

### 7.2 Text analysis

1. The user opens **Analyze** and selects **Enter text**.
2. The app validates non-empty text and the 5,000-character limit.
3. Optional platform and sender-alias fields are clearly labeled as user-entered and unverified.
4. The app sends the text to `POST /v1/analyses`.
5. The backend preprocesses and classifies it, then applies severity and alert policy.
6. The app presents the result, uncertainty note, and safe next-step guidance.
7. Normal raw text is discarded. Harmful text becomes an encrypted case with a 30-day expiry.

### 7.3 Screenshot analysis

1. The user selects **Scan screenshot** and chooses camera or gallery.
2. The app requests permission only when the selected action requires it.
3. The client normalizes orientation, removes metadata, limits dimensions, and produces JPEG or PNG.
4. The backend validates the MIME signature, file size, and decoded dimensions.
5. Tesseract extracts English text and returns it with OCR confidence.
6. The temporary server upload is deleted in a `finally` path whether OCR succeeds or fails.
7. The user reviews and edits the extracted text.
8. Only the confirmed text is classified.
9. The screenshot is not retained unless the user explicitly attaches it to a harmful case.

### 7.4 Case sharing and review

1. The user opens a harmful case.
2. The case shows the immutable model result, retention date, and any human reviews.
3. The user can add context, attach the screenshot, or request review.
4. Sharing with an organization requires an explicit confirmation naming that organization.
5. The backend creates a scoped `case_share`; it does not copy the case into a separate untracked store.
6. Revoking the share immediately removes organization access.

### 7.5 Account deletion

1. The user re-enters their password and confirms deletion.
2. The backend revokes sessions and deletes owned cases, evidence, alerts, links, and account identifiers in one transaction where possible.
3. Encrypted evidence files are removed from disk.
4. Only de-identified aggregate counters may remain.

## 8. Mobile information architecture

The interface must use a mobile hierarchy rather than compressing a desktop dashboard.

### 8.1 Shared screens

- Launch and local API connection check
- Age screen
- Register and sign in
- Pending Guardian approval
- Analyze method selection
- Text entry
- Camera/gallery selection
- OCR review and correction
- Analysis result
- Case list and filters
- Case detail and human review
- Alert inbox
- Report filters and preview
- Profile, privacy, data export, and deletion

### 8.2 User navigation

Bottom tabs:

1. **Home** — recent activity and safety explanation
2. **Analyze** — text or screenshot input
3. **Cases** — harmful-case history
4. **Alerts** — personal in-app notices
5. **Profile** — links, sharing, privacy, and sign-out

### 8.3 Guardian navigation

Bottom tabs:

1. **Overview** — linked-user summary
2. **Linked users** — links and approvals
3. **Cases** — own and linked-user cases
4. **Alerts** — eligible linked-user alerts
5. **Profile** — privacy and sign-out

### 8.4 School Administrator navigation

Bottom tabs:

1. **Overview** — organization-shared summary
2. **Review** — explicitly shared cases
3. **Reports** — organization-scoped summaries and PDF
4. **Members** — organization membership management
5. **Profile** — privacy and sign-out

### 8.5 Design requirements

- Calm pastel surfaces with WCAG AA text and control contrast.
- Do not communicate risk through color alone; pair it with text and icons.
- Minimum 44-by-44-point touch targets.
- Dynamic text scaling without clipped content.
- Screen-reader labels for every icon, chart, status, and form control.
- Plain-language explanations and no punitive wording.
- Sensitive content hidden behind a deliberate **Reveal** action.
- Loading, empty, permission-denied, offline, timeout, and retry states for every network workflow.

## 9. Planned technical architecture

```text
Expo React Native application
        |
        | JSON and multipart requests on the local network
        v
FastAPI application on the Mac
        |
        |-- Authentication and authorization
        |-- Guardian and organization linking
        |-- OCR preprocessing and Tesseract
        |-- Classification and risk policy
        |-- Cases, alerts, retention, and reports
        |
        |-- SQLite database
        `-- Encrypted local evidence directory
```

### 9.1 Mobile stack

- Expo and React Native with TypeScript
- Expo Router for role-aware navigation
- TanStack Query for API state, retries, and cache invalidation
- React Hook Form and Zod for forms
- Expo SecureStore for refresh tokens
- Expo ImagePicker for camera/gallery access
- Expo FileSystem and Sharing for generated reports
- React Native Testing Library and Jest for component tests

Do not store raw analyzed content in AsyncStorage or query-cache persistence.

### 9.2 Backend stack

- Python 3.11 in Conda environment `a-mbl`
- FastAPI and Uvicorn
- Pydantic request/response models
- SQLAlchemy 2 and Alembic migrations
- SQLite with foreign keys enabled
- Argon2 password hashing
- Signed access and rotating refresh tokens
- Cryptography for sensitive content and evidence encryption
- scikit-learn and joblib for model training/inference
- Tesseract, pytesseract, Pillow, and OpenCV for OCR
- ReportLab for PDF generation
- pytest, HTTPX, Ruff, and mypy for quality checks

### 9.3 Local connection

FastAPI will listen on the Mac network interface during demonstrations:

```bash
conda activate a-mbl
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

The mobile app will use a development-only `EXPO_PUBLIC_API_URL`, for example:

```text
http://192.168.1.20:8000
```

A pre-login connection screen will call `/v1/health`, explain common same-Wi-Fi/firewall problems, and allow the local address to be changed without altering source code.

Because this is a local HTTP prototype, only synthetic accounts and demonstration content may be used. Real sensitive content requires an HTTPS deployment and a separate security review, both outside version one.

## 10. API contract

All endpoints use the `/v1` prefix. FastAPI's OpenAPI document is the source of truth, and TypeScript response types should be generated from it rather than maintained manually.

### 10.1 Authentication and profile

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/v1/health` | Local connectivity and model/OCR readiness |
| POST | `/v1/auth/register` | Create a User or Guardian account |
| POST | `/v1/auth/login` | Issue access and refresh tokens |
| POST | `/v1/auth/refresh` | Rotate the refresh token and issue a new access token |
| POST | `/v1/auth/logout` | Revoke the current refresh token |
| GET | `/v1/me` | Return the authenticated profile and permissions |
| PATCH | `/v1/me` | Update permitted profile fields |

Access tokens expire after 15 minutes. Rotating refresh tokens expire after seven days, are hashed in the database, and are stored on the device with SecureStore.

### 10.2 Links and organizations

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/v1/guardian-links` | Create a 24-hour one-time link code |
| POST | `/v1/guardian-links/accept` | Guardian accepts and approves a link code |
| GET | `/v1/guardian-links` | List links visible to the current account |
| DELETE | `/v1/guardian-links/{id}` | Revoke a link |
| GET | `/v1/organizations` | List organizations available to the account |
| POST | `/v1/cases/{id}/shares` | Explicitly share a case with an organization |
| DELETE | `/v1/cases/{id}/shares/{shareId}` | Revoke organization access |

### 10.3 OCR and analysis

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/v1/ocr` | Validate a screenshot, run OCR, delete the temporary file, and return editable text |
| POST | `/v1/analyses` | Classify user-confirmed text and apply case/alert policy |
| GET | `/v1/analyses/{id}` | Retrieve a result if the current role is authorized |

Planned analysis request:

```ts
interface AnalysisRequest {
  text: string;
  sourceType: "text" | "screenshot";
  platformName?: string;
  senderAlias?: string;
}
```

Planned analysis response:

```ts
type PrimaryLabel =
  | "normal"
  | "offensive"
  | "harassment"
  | "hate_speech"
  | "threat";

type Severity = "safe" | "caution" | "high" | "critical";

interface AnalysisResult {
  id: string;
  primaryLabel: PrimaryLabel;
  confidence: number;
  bodyShaming: boolean;
  severity: Severity;
  needsReview: boolean;
  advice: string[];
  modelVersion: string;
  retainedUntil: string | null;
}
```

### 10.4 Cases, alerts, reports, and privacy

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/v1/cases` | Paginated, filtered role-scoped case list |
| GET | `/v1/cases/{id}` | Authorized case detail |
| PATCH | `/v1/cases/{id}` | Add context or permitted metadata |
| DELETE | `/v1/cases/{id}` | Delete the case and evidence |
| POST | `/v1/cases/{id}/evidence` | Explicitly attach screenshot evidence |
| POST | `/v1/cases/{id}/reviews` | Add a human review without changing model output |
| GET | `/v1/alerts` | Role-scoped in-app alert inbox |
| PATCH | `/v1/alerts/{id}` | Mark an alert read |
| GET | `/v1/reports/summary` | Date/category/severity summary for the current scope |
| POST | `/v1/reports/pdf` | Generate a masked role-scoped PDF |
| GET | `/v1/privacy/export` | Export the authenticated account's data |
| DELETE | `/v1/privacy/account` | Confirm and delete the account and owned data |

### 10.5 Error format

All non-success responses use a consistent body:

```json
{
  "code": "validation_error",
  "message": "The request could not be processed.",
  "fieldErrors": {
    "text": "Text must not be empty."
  },
  "requestId": "generated-request-id"
}
```

Required error handling includes `400`, `401`, `403`, `404`, `409`, `413`, `422`, `429`, and `500`. Internal errors must not return file paths, stack traces, raw content, tokens, or encryption details.

## 11. Planned database model

| Entity | Important data and rules |
| --- | --- |
| `users` | Email, password hash, role, age band, status, timestamps; no raw password or full date of birth |
| `organizations` | Name, status, timestamps |
| `organization_memberships` | User, organization, organization role, status; unique membership constraint |
| `guardian_links` | User, Guardian, status, consent time, revoked time; only one active matching relationship |
| `guardian_link_codes` | Hashed one-time code, creator, expiry, consumed time |
| `refresh_tokens` | Token hash, user, expiry, revocation, rotation chain |
| `analysis_events` | Owner, primary label, confidence, tag, severity, model version, time; Normal raw text is always null |
| `flagged_cases` | Harmful analysis reference, encrypted confirmed text, review status, optional metadata, 30-day expiry |
| `case_evidence` | Random file identifier, encrypted path, content hash, MIME type, size, expiry |
| `case_shares` | Case, organization, sharer, shared/revoked timestamps |
| `review_events` | Case, reviewer, human label, encrypted note, timestamp; original model result remains unchanged |
| `alerts` | Recipient, case, severity, read time; no raw text in preview fields |
| `model_versions` | Artifact checksum, label map, thresholds, metrics, creation time |
| `audit_events` | Actor, action, object type/id, timestamp; no raw content or secrets |

SQLite foreign keys must be enabled. Authorization filters must be applied before records are serialized. File deletion and database deletion must be coordinated so failed cleanup can be retried safely.

## 12. AI model plan

### 12.1 Data preparation

1. Use only public datasets with clear redistribution and research-use terms.
2. Record each dataset's origin, license, version, labels, and known limitations in a dataset card.
3. Map compatible examples to the five primary labels using a written annotation guide.
4. Manually review Harassment mappings and Body Shaming tags because they do not map cleanly from generic toxicity labels.
5. Remove exact and near-duplicate text before splitting.
6. Split by source group into fixed 70% training, 15% validation, and 15% test sets.
7. Never place synthetic augmentation in validation or test data.
8. Keep raw and processed datasets outside Git; track scripts, manifests, hashes, and documentation instead.

### 12.2 Baseline model

Start with a CPU-friendly, explainable baseline:

- Word and character TF-IDF features
- Class-weighted Logistic Regression for the five-class result
- Calibrated probabilities for confidence and threshold policy
- A separate one-vs-rest classifier for Body Shaming
- A versioned preprocessing pipeline saved with joblib

Character features are important for misspellings and obfuscated abusive terms. The model must not use optional sender or platform metadata as predictive features.

### 12.3 Evaluation

Report:

- Overall accuracy
- Macro and weighted F1
- Per-class precision, recall, and F1
- Confusion matrix
- False-positive rate
- Threat recall
- Confidence calibration
- Error slices for dialect, slang, reclaimed language, identity terms, and obfuscation
- Warm and cold inference latency on the development Mac

Validation targets, not pre-existing achievements:

- Accuracy at least 85%
- Overall false-positive rate below 10%
- Macro-F1 at least 0.75
- Threat recall at least 0.80

If the baseline misses the gate, the predefined next experiment is a compact DistilRoBERTa classifier. PyTorch and Transformers should be added to the environment only at that point. If the final model still misses the target, the app remains usable as an experimental prototype but must display the limitation and report the measured results honestly.

### 12.4 Model result language

Use wording such as:

- “The submitted text may contain harassment signals.”
- “This result is uncertain and should be reviewed.”
- “If someone may be in immediate danger, contact a trusted person or an appropriate local service.”

Do not use wording such as “This person is a bully,” “A crime occurred,” or “The system has confirmed a threat.”

## 13. OCR plan

1. Validate file signature, decoded image type, size, and dimensions.
2. Normalize orientation and remove metadata on the device.
3. Create grayscale and contrast-enhanced variants with OpenCV.
4. Correct simple rotation/skew where confidence improves.
5. Run Tesseract with English language data.
6. Return extracted text, mean confidence, and a low-confidence warning.
7. Require user confirmation before classification.
8. Delete temporary files on success, validation error, timeout, cancellation, or exception.

OCR acceptance fixtures should include clean screenshots, dark mode, low contrast, rotated text, long messages, empty images, unsupported files, and images containing unrelated private content near the target message.

## 14. In-app alerts

Alerts are records inside the app, not remote device notifications.

### 14.1 Creation rules

- The owner receives the result immediately on the result screen.
- High/Critical cases at or above the alert threshold create an alert for an active linked Guardian.
- A School Administrator receives an alert only when the case is already shared with their organization.
- Low-confidence results do not alert linked roles automatically.
- Reprocessing the same case/model version must not create duplicate alerts.

### 14.2 Display rules

- The alert list shows severity, primary category, subject account, and time.
- It never includes raw content or screenshot thumbnails.
- Opening the alert performs a fresh authorization check before loading the case.
- The client refreshes alerts when the app enters the foreground and through a light polling interval while the inbox is open.

## 15. Reports and analytics

### 15.1 In-app summaries

Provide:

- Total harmful cases for a selected date range
- Counts by primary category and severity
- Weekly trend
- Reviewed versus pending cases
- Optional grouping by user-entered sender alias, clearly marked as unverified

Every chart requires a text/table alternative for accessibility. Do not calculate a definitive “offender score” or “child safety score.”

### 15.2 Masked PDF report

The backend generates a PDF containing:

- Report scope and date range
- Creation timestamp
- Category and severity summary
- Case IDs and timestamps
- Model label, confidence, Body Shaming tag, and review status
- Masked content preview
- Human review notes only when the requester is authorized
- A statement that classifications are automated estimates

The default PDF must not contain passwords, account tokens, email addresses, full raw messages, full screenshots, local file paths, or encryption metadata. The server deletes temporary PDF files after download or expiry.

## 16. Privacy, security, and retention

### 16.1 Data minimization

- Store no raw Normal text or screenshot.
- Store harmful confirmed text only inside an encrypted case.
- Store a screenshot only after explicit attachment.
- Collect age band rather than a full birth date after screening.
- Keep optional platform and sender-alias fields empty by default.
- Never write raw submitted text to logs, analytics, exceptions, or audit records.

### 16.2 Retention

- Harmful cases and evidence expire 30 days after creation.
- Show the deletion date on the case screen.
- A user can delete a case earlier.
- Cleanup runs at backend startup and every 24 hours while the backend remains active.
- Failed file cleanup is recorded without logging the sensitive path and is retried.

### 16.3 Authentication and local storage

- Hash passwords with Argon2.
- Use 15-minute access tokens and rotating seven-day refresh tokens.
- Hash refresh tokens in SQLite and revoke the previous token on rotation.
- Store the mobile refresh token in SecureStore, never AsyncStorage.
- Keep encryption keys and local database/evidence paths outside Git.
- Rate-limit login, OCR, and analysis endpoints.

### 16.4 Prototype limitation

The local same-Wi-Fi connection is a development convenience and does not provide a production security boundary. Use synthetic demonstration accounts and content only. A real deployment would require HTTPS, secured secret management, hardened hosting, backups, monitoring, formal policy review, and independent legal/security assessment.

## 17. Fourteen-week implementation roadmap

### Weeks 1–2: Foundation and interface design

Deliverables:

- Create `mobile/`, `backend/`, and `ml/` structures.
- Establish Node/Expo and Conda workflows.
- Define Pydantic/OpenAPI contracts and generate initial TypeScript types.
- Implement `/v1/health` and the mobile connection screen.
- Produce low-fidelity flows for all roles and core error states.
- Define the database model, retention rules, taxonomy, and annotation guide.
- Seed synthetic roles and organizations.

Exit criteria:

- Android and iPhone Expo Go clients can reach the Mac API.
- Role navigation and API contracts have no unresolved behavior decisions.
- Synthetic fixtures cover each category and role.

### Weeks 3–4: Dataset, baseline model, and OCR proof

Deliverables:

- Dataset license/version manifest and label mapping.
- Deduplication and fixed train/validation/test pipeline.
- TF-IDF baseline and Body Shaming classifier.
- Calibration, metric report, confusion matrix, and model card.
- Tesseract preprocessing experiment and OCR fixture suite.
- Versioned model artifact loading in FastAPI.

Exit criteria:

- Training and evaluation reproduce from documented commands.
- No data leakage is found between splits.
- OCR returns editable text and deletes temporary files.
- Actual model gaps are recorded before UI claims are written.

### Weeks 5–6: Backend foundation

Deliverables:

- SQLAlchemy entities and Alembic migrations.
- Registration, login, refresh, logout, and profile endpoints.
- Guardian codes, approval, revocation, and organization membership.
- Role-based authorization dependencies and scoped query helpers.
- OCR and analysis endpoints.
- Encryption, case creation, retention cleanup, and audit events.

Exit criteria:

- API tests prove cross-role and cross-organization isolation.
- Normal raw text is absent from SQLite and local files.
- Harmful cases encrypt, decrypt for authorized users, and expire correctly.

### Weeks 7–8: Core mobile analysis experience

Deliverables:

- Authentication and pending-account screens.
- Role-aware Expo Router groups.
- Text input, validation, and result screens.
- Camera/gallery permission handling.
- Screenshot normalization, OCR upload, correction, and analysis flow.
- Secure token storage and refresh handling.
- Offline, timeout, permission-denied, and retry states.

Exit criteria:

- Text and screenshot flows work on physical Android and iPhone devices.
- The UI never caches raw analyzed content persistently.
- Every result clearly distinguishes model output from human judgment.

### Weeks 9–10: Cases, roles, sharing, and alerts

Deliverables:

- Role-scoped case lists and detail screens.
- Human review records and immutable model output.
- Guardian linking screens.
- Organization sharing and revocation.
- Risk-tiered alert creation and inbox.
- Evidence attachment and deletion.

Exit criteria:

- Guardian access is limited to active links.
- Administrator access is limited to explicitly shared organization cases.
- Alert previews reveal no raw content.
- Duplicate processing cannot create duplicate alerts.

### Weeks 11–12: Reports, privacy controls, and accessibility

Deliverables:

- Date/category/severity report filters.
- Accessible summaries and charts.
- Masked PDF generation, download, and sharing.
- Data export, case deletion, account deletion, and retention visibility.
- Screen-reader, text-scaling, contrast, and touch-target improvements.
- Security and privacy logging review.

Exit criteria:

- Reports contain only data visible to the requesting role.
- PDFs contain no unmasked raw evidence by default.
- Retention cleanup and deletion remove both database records and files.
- Critical screens pass the accessibility checklist.

### Weeks 13–14: Validation, fixes, and handoff

Deliverables:

- Full unit, API, mobile, ML, OCR, and end-to-end test runs.
- Latency and model-quality report using the final artifacts.
- Threat/false-positive and subgroup error review.
- Physical Android and iPhone acceptance checklist.
- Synthetic demo accounts and safe demonstration scenarios.
- Final setup, troubleshooting, and operating documentation.

Exit criteria:

- No unresolved critical authorization, privacy, deletion, or crash defect.
- Actual model metrics and known limitations are visible in documentation.
- The complete demonstration can be repeated from a clean setup.

## 18. Test strategy

### 18.1 Mobile tests

- Form validation and accessible labels
- Role-aware navigation
- Token expiry and refresh
- Camera/gallery denial and cancellation
- OCR correction and empty OCR results
- API unavailable, IP changed, timeout, and retry
- Sensitive-content reveal controls
- Report download/share errors
- Account and case deletion confirmation

Use Jest and React Native Testing Library for unit/component coverage. Use an Android emulator for repeatable automated flows and a manual physical-iPhone Expo Go checklist for final acceptance.

### 18.2 API tests

- Registration and age-band behavior
- Login throttling, password hashing, refresh rotation, and logout
- Guardian-code expiry, one-time use, approval, and revocation
- School Administrator creation restrictions
- IDOR and cross-organization attempts on every case/report endpoint
- Text limits, unsupported MIME types, spoofed files, oversized images, and malformed images
- Normal-content non-retention
- Encryption/decryption authorization
- 30-day cleanup and deletion cascades
- Alert thresholds, scope, and deduplication
- PDF masking and temporary-file cleanup

Use pytest and HTTPX with a temporary SQLite database and temporary evidence directory for every test run.

### 18.3 Model and OCR tests

- Deterministic preprocessing and fixed split hashes
- No exact or near-duplicate leakage
- Five-class and Body Shaming output shapes
- Probability calibration and threshold behavior
- Per-class metrics and confusion cases
- Slang, identity term, obfuscation, and benign profanity error slices
- Clear, dark-mode, rotated, low-contrast, empty, and noisy screenshots
- No synthetic example in the final test set

### 18.4 Performance checks

Measure at least 30 warmed same-Wi-Fi requests on the development Mac:

- Text analysis p95 target: at most 2 seconds
- Screenshot OCR plus analysis p95 target: at most 5 seconds after user confirmation is excluded
- API error rate target during the controlled test run: 0% for valid requests

Record device model, Mac hardware, network conditions, dataset/model version, and sample size with the results.

### 18.5 Documentation and repository checks

- TypeScript types match the current OpenAPI document.
- Setup commands work from a clean clone.
- No secrets, databases, datasets, trained artifacts, evidence, or raw reports are tracked in Git.
- No tracked document claims unmeasured accuracy or production readiness.
- Markdown links and code blocks render correctly.

## 19. Key risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| False positive | Unnecessary concern or unfair interpretation | Calibrated confidence, uncertainty state, human review, cautious language |
| False negative | Harmful content may be missed | Per-class recall tracking, prominent limitations, safe guidance, manual flagging |
| Weak Harassment labels | Model may confuse insults and targeted abuse | Written annotation guide and manual mapping review |
| Body Shaming data scarcity | Unstable secondary tag | Separate evaluation and no alert escalation unless the tag meets its quality gate |
| OCR error | Wrong text may be classified | Mandatory OCR review/edit step before analysis |
| Dataset bias | Unequal error rates across language styles or groups | Error slicing, model card, hard-negative review, no definitive judgments |
| Role-data leakage | Sensitive cases exposed to the wrong account | Backend-scoped queries, IDOR tests, explicit shares, audit events |
| Local HTTP connection | Data can be exposed on an untrusted network | Synthetic demo data only and same trusted Wi-Fi |
| Changing Mac IP | Mobile app cannot reach the API | Editable connection screen and health diagnostics |
| Expo Go limitations | No true remote notifications or standalone iPhone package | In-app alerts only; signed builds remain outside version one |
| Scope creep | Prototype becomes too complex to finish | Enforce the exclusions and phase exit criteria in this roadmap |

## 20. Definition of done

Version one is done only when all of the following are true:

- Android and iPhone complete the core flows through Expo Go on the same Wi-Fi as the Mac.
- Text and screenshot/OCR analysis work end to end.
- The API returns the five primary categories and Body Shaming tag using a versioned model.
- Users, Guardians, and School Administrators can access only their defined scopes.
- Guardian consent and organization sharing can be created and revoked.
- Normal raw content is not retained.
- Harmful cases and attached evidence are encrypted, visible only to authorized roles, and removed after 30 days or earlier deletion.
- Risk-tiered in-app alerts contain no raw content and do not duplicate.
- Reports and PDFs enforce role scope and masking.
- Account deletion removes the account's identifiable content and sessions.
- Critical automated tests pass, physical-device checks pass, and no critical defect remains.
- Model accuracy, false-positive rate, per-class performance, latency, and known limitations are reported from real tests.
- Documentation does not claim cloud deployment, store availability, production readiness, guaranteed detection, or legal compliance.
