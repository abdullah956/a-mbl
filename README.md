# a-mbl

`a-mbl` is a mobile application for reviewing user-submitted text and chat screenshots for possible cyberbullying signals. The product is designed to provide clear, cautious results, support human review, and help users share selected cases with trusted guardians or authorized school administrators.

> **Status:** Version 0.2.0 is implemented and working locally — Expo mobile app (runs in Expo Go or as an installable Android APK), FastAPI backend, SQLite storage, encryption, retention, in-app and optional email alerts, a Home dashboard with charts, reports, screenshot OCR, and a 120-test backend suite. Classification is a hybrid: a trained TF-IDF model (`tfidf-logreg-0.2.0`, built by `ml/train.py`) merged with the deterministic lexicon baseline. The model is trained and active on the development Mac (`/v1/health` reports `tfidf-logreg-0.2.0` there). The model file `ml/artifacts/model.joblib` stays out of Git, so a fresh clone runs the lexicon baseline (`lexicon-0.1.0`) alone until the model is trained or the file is copied in (see [ml/README.md](ml/README.md)).

## Capabilities (v0.2.0)

- Analyze manually entered English text (up to 5,000 characters).
- Extract editable text from a camera or gallery screenshot before analysis (Tesseract OCR; the scan flow appears once the server reports it is ready).
- Classify content as Normal, Offensive, Harassment, Hate Speech, or Threat, with a confidence score and cautious wording.
- Add Body Shaming as a separate secondary tag.
- Role-based experiences for Users, Guardians, and School Administrators, enforced by backend query scoping.
- Keep harmful cases encrypted in a private review history with risk-tiered in-app alerts (no raw content in previews), plus optional email alerts to linked guardians and school administrators (never containing message content).
- Show a role-scoped Home dashboard (cases per week, cases by day of week, top repeat senders by user-entered alias) and generate role-scoped summaries and masked PDF reports.
- Minimize retained content: Normal text is discarded immediately; harmful cases expire after 30 days; account and case deletion remove data and evidence files.

This version does not monitor other applications, intercept messages, connect to social-media accounts, send push or SMS alerts, or publish to an app store (testers install a sideloaded APK instead). Email alerts are optional and off by default: they are sent only when the server owner configures an SMTP mailbox (see [docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md)).

## Technology

| Area | Technology |
| --- | --- |
| Mobile | Expo (SDK 57), React Native, TypeScript, Expo Router |
| Local API | Python 3.11, FastAPI, Uvicorn |
| Storage | SQLite + Fernet-encrypted local evidence files |
| Classification | Hybrid: trained TF-IDF + logistic regression (scikit-learn, `tfidf-logreg-0.2.0`, loaded from `ml/artifacts/model.joblib`) merged severity-max with the lexicon baseline `lexicon-0.1.0`, which runs alone when the artifact is absent |
| Email alerts | Python `smtplib`, optional, configured with `A_MBL_SMTP_*` environment variables |
| Screenshot OCR | Tesseract + Pillow (feature-flagged via `/v1/health`) |
| Reports | ReportLab PDF generation |
| Android build | Expo prebuild + Gradle → standalone release APK (`npm run build:apk`) |

## Quick start

Backend, in a Conda environment named `a-mbl`:

```bash
conda create -n a-mbl python=3.11 -y
conda activate a-mbl
pip install -r backend/requirements.txt
conda install -c conda-forge tesseract  # optional: enables screenshot OCR

python -m pytest backend/tests          # run the test suite
python -m backend.scripts.seed_demo     # optional: synthetic demo accounts
./backend/run.sh                        # serve on 0.0.0.0:8000 and print the Mac's address
```

On Windows, `.\backend\run.ps1` in PowerShell does the same job as `run.sh` (see [docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md)). To switch on the trained classifier, place `model.joblib` in `ml/artifacts/` or train it with `python ml/train.py` (needs the Jigsaw `train.csv`, from Kaggle or from a Hugging Face mirror that needs no account; steps in [ml/README.md](ml/README.md)), then restart the backend. `/v1/health` reports the active `modelVersion`.

Mobile, with a Node.js LTS release:

```bash
cd mobile
npm install
npx expo start
```

Open the project in **Expo Go** on an Android phone or iPhone on the same Wi-Fi as the Mac, then enter the server address printed by `run.sh` (for example `http://192.168.1.20:8000`) on the app's connection screen. School administrator accounts are created with `python -m backend.scripts.create_admin` (see [docs/IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md)).

To give a tester an installable Android app instead, run `npm run build:apk` in `mobile/` (needs JDK 17 and the Android SDK) and send `dist/a-mbl-0.2.0.apk`; [docs/DEVICE_TESTING.md](docs/DEVICE_TESTING.md) covers building, sending, and running a remote session.

This local connection is intended for synthetic demonstration data only. It is not a production deployment.

## Repository layout

```text
a-mbl/
├── mobile/                 # Expo React Native application (+ scripts/build-apk.sh, scripts/check-casing.mjs)
├── backend/                # FastAPI API, storage, policy, reports, email alerts, tests (+ run.sh, run.ps1)
├── ml/                     # Training pipeline (train.py) and results; data and trained artifacts stay out of Git
├── docs/                   # How to run, device testing, architecture, flows, roadmap, notes
├── tests/fixtures/         # Shared labeled samples for classifier tests
├── CLIENT_GUIDE.md         # Non-technical guide for clients and testers
├── PROJECT_GUIDE.md        # Complete technical guide (every file, endpoint, table, test)
└── README.md
```

Generated, gitignored folders: `backend/data/` (database, keys, encrypted evidence), `ml/data/` (the downloaded training data), `ml/artifacts/` (`model.joblib`, metrics, confusion matrix), `mobile/android/` (regenerated by prebuild), and `dist/` (built APKs).

## Documentation

- [Client Guide](CLIENT_GUIDE.md) — non-technical explanation of the whole app, with diagrams, screenshots, and a test script for clients.
- [Project Guide](PROJECT_GUIDE.md) — the complete technical walkthrough of every file, endpoint, table, screen, and test.
- [How to Run](docs/HOW_TO_RUN.md) — setup, start commands, demo accounts, tests, and troubleshooting.
- [Device Testing](docs/DEVICE_TESTING.md) — Expo Go on your phone, building and sending the Android APK, remote sessions, iPhone options.
- [Screen Flows](docs/FLOWS.md) — every role's screen flow and error states.
- [Architecture](docs/ARCHITECTURE.md) — system diagram, module map, key flows, data model, and the day-to-day workflow.
- [Mobile Application Roadmap](docs/MOBILE_APP_ROADMAP.md) — full product scope, architecture, policies, and the fourteen-week plan.
- [Implementation Notes](docs/IMPLEMENTATION_NOTES.md) — what is built and every deviation from the roadmap with its reason.
- [Report Reconciliation](docs/REPORT_RECONCILIATION.md) — what the proposal promised versus what was built, with suggested wording for the report and slides.
- [ml/README.md](ml/README.md) — the trained classifier: how it fits the hybrid, its recorded test results, and how to retrain it.

## Privacy and safety limitations

- Model output is an estimate for review, not a final judgment about a person or incident. The trained model's held-out results, measured on the development Mac and recorded in [ml/README.md](ml/README.md): accuracy 0.903 and false-positive rate 0.053 meet their targets, but threat recall 0.718 and macro F1 0.558 fall short, and the data is Wikipedia discussion comments, not teen chat. The lexicon baseline on its own has no measured accuracy, and it is what the server uses whenever `model.joblib` is absent.
- Normal raw content is discarded immediately after analysis and never stored.
- Harmful cases expire after 30 days unless the user deletes them sooner.
- Screenshots are retained only when a user explicitly attaches one to a harmful case, and are stored encrypted.
- No case is shared with a school administrator without explicit, revocable authorization.
- The prototype must not be used with real sensitive or minor-related content over an unsecured local connection.
- The project does not claim production readiness or legal compliance.
