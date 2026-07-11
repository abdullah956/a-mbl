# a-mbl

`a-mbl` is a mobile application for reviewing user-submitted text and chat screenshots for possible cyberbullying signals. The product is designed to provide clear, cautious results, support human review, and help users share selected cases with trusted guardians or authorized school administrators.

> **Status:** Version 0.1 is implemented and working locally — Expo mobile app, FastAPI backend, SQLite storage, encryption, retention, alerts, reports, and an 86-test suite. The trained classification model is still to come: v0.1 uses an honest, deterministic lexicon baseline (see [ml/README.md](ml/README.md)). OCR activates automatically once Tesseract is installed on the Mac.

## Capabilities (v0.1)

- Analyze manually entered English text (up to 5,000 characters).
- Extract editable text from a camera or gallery screenshot before analysis (when Tesseract is installed).
- Classify content as Normal, Offensive, Harassment, Hate Speech, or Threat, with a confidence score and cautious wording.
- Add Body Shaming as a separate secondary tag.
- Role-based experiences for Users, Guardians, and School Administrators, enforced by backend query scoping.
- Keep harmful cases encrypted in a private review history with risk-tiered in-app alerts (no raw content in previews).
- Generate role-scoped summaries and masked PDF reports.
- Minimize retained content: Normal text is discarded immediately; harmful cases expire after 30 days; account and case deletion remove data and evidence files.

This version does not monitor other applications, intercept messages, connect to social-media accounts, send remote push/SMS/email alerts, or publish to an app store.

## Technology

| Area | Technology |
| --- | --- |
| Mobile | Expo (SDK 57), React Native, TypeScript, Expo Router |
| Local API | Python 3.11, FastAPI, Uvicorn |
| Storage | SQLite + Fernet-encrypted local evidence files |
| Classification | Lexicon baseline `lexicon-0.1.0` (planned: calibrated TF-IDF model) |
| Screenshot OCR | Tesseract + Pillow (feature-flagged via `/v1/health`) |
| Reports | ReportLab PDF generation |

## Quick start

Backend, in a Conda environment named `a-mbl`:

```bash
conda create -n a-mbl python=3.11 -y
conda activate a-mbl
pip install -r backend/requirements.txt

python -m pytest backend/tests          # run the test suite
python -m backend.scripts.seed_demo     # optional: synthetic demo accounts
./backend/run.sh                        # serve on 0.0.0.0:8000 and print the Mac's address
```

Mobile, with a Node.js LTS release:

```bash
cd mobile
npm install
npx expo start
```

Open the project in **Expo Go** on an Android phone or iPhone on the same Wi-Fi as the Mac, then enter the server address printed by `run.sh` (for example `http://192.168.1.20:8000`) on the app's connection screen. School administrator accounts are created with `python -m backend.scripts.create_admin` (see [docs/IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md)).

This local connection is intended for synthetic demonstration data only. It is not a production deployment.

## Repository layout

```text
a-mbl/
├── mobile/                 # Expo React Native application
├── backend/                # FastAPI API, storage, policy, reports, tests
├── ml/                     # Model plan; trained artifacts stay out of Git
├── docs/                   # Roadmap and implementation notes
├── tests/fixtures/         # Shared labeled samples for classifier tests
└── README.md
```

## Documentation

- [How to Run](docs/HOW_TO_RUN.md) — setup, start commands, demo accounts, tests, and troubleshooting.
- [Architecture](docs/ARCHITECTURE.md) — system diagram, module map, key flows, data model, and the day-to-day workflow.
- [Mobile Application Roadmap](docs/MOBILE_APP_ROADMAP.md) — full product scope, architecture, policies, and the fourteen-week plan.
- [Implementation Notes](docs/IMPLEMENTATION_NOTES.md) — what v0.1 contains and every deviation from the roadmap with its reason.

## Privacy and safety limitations

- Model output is an estimate for review, not a final judgment about a person or incident. The v0.1 lexicon baseline has no measured accuracy.
- Normal raw content is discarded immediately after analysis and never stored.
- Harmful cases expire after 30 days unless the user deletes them sooner.
- Screenshots are retained only when a user explicitly attaches one to a harmful case, and are stored encrypted.
- No case is shared with a school administrator without explicit, revocable authorization.
- The prototype must not be used with real sensitive or minor-related content over an unsecured local connection.
- The project does not claim production readiness or legal compliance.
