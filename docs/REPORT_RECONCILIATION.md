# Report reconciliation — proposal vs. what was built

This document is for whoever updates the TM471 report and slides. It lists, per
section, what the proposal promised, what the implemented system actually does,
and suggested replacement wording. Everything here is verifiable in this
repository — nothing is aspirational.

## 1. Technology stack (report §3.4, slide "Technology Stack and Tools")

| Area | Proposal said | As built | Why the change is defensible |
| --- | --- | --- | --- |
| Front end | HTML5, CSS3, JavaScript, Bootstrap | **React Native + Expo (TypeScript)** — a native mobile app for Android and iOS from one codebase | The product analyzes private chat content; a phone app is where that content lives. One codebase still covers both platforms. |
| Backend | Flask or Django or Node.js | **FastAPI (Python)** | Same Python ecosystem the proposal assumed; FastAPI adds typed request validation and generated API docs. |
| Database | MySQL or MongoDB | **SQLite + Fernet-encrypted evidence files** | Zero-setup local prototype by design; case text is encrypted at rest, which MySQL alone would not provide. |
| AI/ML | TensorFlow or PyTorch, NLTK, Scikit-learn | **scikit-learn** (TF-IDF + calibratable logistic regression) hybridized with a lexicon | Scikit-learn was already on the proposal's list. Deep-learning frameworks remain future work (see §5). |
| OCR | Tesseract | **Tesseract** | Matches. |
| Charts | Chart.js | **Custom React Native chart components** | Chart.js is browser-only; the dashboard is native mobile. |
| Passwords | bcrypt (NFR2) | **PBKDF2-HMAC-SHA256, per-user salt** | Same goal (slow, salted hashing); PBKDF2 is in the Python standard library. The report should name the actual algorithm. |

Suggested sentence for the report: *"The stack was revised during implementation
to a React Native (Expo) mobile client and a FastAPI backend with SQLite and
Fernet-encrypted evidence storage; classification uses a scikit-learn TF-IDF
pipeline merged with a curated lexicon. All revisions are documented with
reasons in the repository."*

## 2. Functional requirements scorecard (report Table 3)

| # | Requirement | Status | Wording to use |
| --- | --- | --- | --- |
| 1 | User registration, roles | **Done** | Children (with guardian activation), guardians, and school administrators; role-based visibility is enforced in SQL on every query. |
| 2 | Text input analysis | **Done** | Up to 5,000 characters, analyzed in real time. |
| 3 | Screenshot upload + OCR | **Done** | Tesseract extracts text; the user reviews and corrects it before anything is classified; the image is not retained unless explicitly attached to a case as evidence (then stored encrypted). |
| 4 | AI classification, 5 categories | **Done** | Normal, Offensive, Harassment, Hate Speech, Threat, plus a separate Body Shaming tag. Hybrid: trained model + lexicon safety net (see §4). |
| 5 | Alerts (email/SMS) | **Email done; SMS out of scope** | In-app alerts always; email alerts to linked guardians / school admins when the operator configures an SMTP mailbox. Alerts never contain message content. SMS would require a paid gateway and is listed as future work. |
| 6 | Content flagging + human review | **Done** | Harmful cases are stored encrypted with a 30-day expiry; the model verdict is immutable and human reviews are recorded separately. |
| 7 | Action proposals | **Done (as guidance)** | The app advises (keep evidence, involve a trusted adult, report on the platform, no obligation to respond). It cannot block users on other platforms — no third-party app can — so wording should say "recommends actions" rather than "blocks users". |
| 8 | Report generation | **Done** | Role-scoped summary API, dashboard (trends per week, day-of-week distribution, repeat senders), and masked PDF export. |
| 9 | Admin panel | **Done (scoped)** | School admins review cases explicitly shared with their organization and see scoped analytics. Account deletion is user-initiated (privacy by design) rather than admin-controlled. |

## 3. Non-functional requirements (report Table 4)

- **Usability:** met — calm pastel palette, severity always shown as icon + label + color (never color alone).
- **Security:** passwords PBKDF2-HMAC-SHA256 (salted); case text and evidence encrypted at rest (Fernet). Transport on the local demo network is HTTP; the report should state this as a documented prototype limitation, with HTTPS arriving only with real hosting (future work). No production or legal-compliance claim is made; GDPR/COPPA-aligned *features* exist: guardian consent for minors, minimal retention, full deletion.
- **Performance:** text analysis returns in well under the required 2 s locally (typically tens of milliseconds); OCR typically under 5 s for phone screenshots.
- **Accuracy:** see §4 — this is the section that must be rewritten honestly.
- **Reliability:** "99.9% uptime" is not meaningful for a local prototype. Suggested replacement: "verified by an automated suite of 92 backend tests covering auth, classification, policy, alerts, retention, privacy, reports, and OCR."
- **Responsiveness:** the proposal said "mobile, tablet and desktop browsers"; the delivered client is a native mobile app (Android now, iOS-capable from the same code). Update the wording.
- **Privacy:** met and stricter than proposed — Normal text is discarded immediately and never stored; harmful cases expire after **30 days** (the report's §3.7 said one year; 30 days is the implemented, stricter value).

## 4. Evaluation — replacement text for the accuracy objective

The proposal committed to "at least 85% accuracy with a false positive rate
below 10%". Paste-ready findings:

> **Dataset.** The classifier was trained on the Jigsaw Toxic Comment dataset
> (159,571 human-annotated comments). Its six binary labels were collapsed to
> the project's five classes by severity (threat > identity hate > insult >
> toxic/obscene > normal). The data is 89.8% Normal; Threat has only 478
> examples.
>
> **Headline results** (held-out test set of 23,936 comments at the real class
> distribution): **accuracy 90.6%** (target ≥ 85% — met) and **false-positive
> rate 4.8%** (target < 10% — met). However, the evaluation showed that
> accuracy is a misleading headline metric on this data: a model that labels
> everything Normal scores 90% while detecting nothing. The evaluation
> therefore also reports **macro F1 = 0.57** and **threat recall = 0.66**,
> which fall short of internal targets (0.75 and 0.80) and are presented as
> honest limitations driven mainly by class scarcity (478 threat examples) and
> domain mismatch (Wikipedia discussion comments vs. teen chat messages).
>
> **Method.** A naive model reached 93.4% accuracy but caught only 37% of
> threats. Two corrections were applied: the Normal class was downsampled in
> the training split only (test data keeps the real distribution), and
> per-class decision thresholds were tuned on a validation split — the Threat
> class deliberately receives a low threshold (0.15) because a missed threat
> costs more than a false alarm. Threat recall rose from 0.37 to 0.66 while
> the false-positive rate stayed within budget.
>
> **Hybrid design.** The deployed classifier merges two detectors and keeps
> whichever verdict is more severe: the trained model (catches implicit
> phrasing such as "I will find out where you live", and obfuscations like
> "k*ll") and a curated lexicon (catches explicit phrases the model misses,
> supplies the matched terms used to censor previews, and provides the Body
> Shaming tag, for which no public dataset exists). Deliberately obfuscated
> spellings ("l0ser") *raise* confidence, since evading a filter is itself
> evidence of intent. Low-confidence detections are flagged "needs review" —
> the human-in-the-loop requirement from the proposal's ethics section.

Figures for the report: `ml/artifacts/confusion_matrix.png` (test-set confusion
matrix), `ml/artifacts/metrics.json` (all numbers, including per-class
precision/recall), `ml/artifacts/metrics_naive_baseline.json` (the before
side of the before/after comparison).

## 5. Scope statement (fixes the "monitors social media" framing)

The abstract and slides imply automatic monitoring of social platforms. The
system as designed and built is **victim-driven**: the user pastes text or
uploads a screenshot, and the system classifies, stores evidence encrypted,
alerts linked adults, and reports. This should be stated plainly, and it is a
strength, not a retreat — the report's own literature review documents why the
alternatives fail: keyword-only tools (ReThink) miss coded language; API-based
monitors (BullyBlocker) died when platform APIs were restricted; intercept-all
monitors (Roblox Sentinel) raise the privacy objections the report itself
raises. Suggested sentence: *"The platform is platform-independent because it
accepts text and screenshots from any source, rather than integrating with —
and depending on — any specific social network's API."*

## 6. Small corrections checklist

- Slide 8 (workflow): "MySQL database" → "SQLite database (encrypted evidence files)".
- Objective 4's "automated auditory alarm" → "automated alerts (in-app, plus optional email to guardians/school officials)".
- §3.7 "flagged content removed after a year" → "harmful cases expire after 30 days; users can delete sooner".
- Anywhere "bcrypt" appears → "PBKDF2-HMAC-SHA256 (salted)".
- Comparison table row "Accuracy: Target 85%+" → "90.6% accuracy / 4.8% FPR (measured); macro F1 0.57 reported as limitation".

## 7. Future work (honest, one paragraph)

Hosted deployment with HTTPS and real accounts (removes the local-server
requirement); a fine-tuned transformer classifier compared against the TF-IDF
baseline (the proposal's TensorFlow/PyTorch intent); SMS/push alert channels;
a labeled body-shaming dataset; iOS distribution via the existing shared
codebase (TestFlight requires an Apple Developer account).
