# How to run a-mbl

Everything runs on your Mac; phones connect over the same Wi-Fi through Expo Go
or the installable Android APK. Three terminals at most: backend, mobile
bundler, and occasional commands. The backend can also run on a Windows PC
(see "On Windows" in §2).

## 0. Prerequisites (one time)

| Tool | Check | Install if missing |
| --- | --- | --- |
| Conda (miniconda is fine) | `conda --version` | https://docs.conda.io |
| Node.js LTS + npm | `node --version` | https://nodejs.org |
| Expo Go app on each phone | — | App Store / Play Store |
| Tesseract (optional, enables screenshot OCR) | `conda run -n a-mbl tesseract --version` | `conda install -n a-mbl -c conda-forge tesseract` |
| JDK 17 + Android SDK (only to build the APK) | `conda run -n a-mbl java -version` | `conda install -n a-mbl -c conda-forge openjdk=17`; the SDK comes with Android Studio |

## 1. One-time setup

From the repository root:

```bash
# Backend: Python 3.11 environment named a-mbl
conda create -n a-mbl python=3.11 -y
conda activate a-mbl
pip install -r backend/requirements.txt
conda install -c conda-forge tesseract     # optional: screenshot OCR

# Mobile: JavaScript dependencies
cd mobile && npm install && cd ..
```

## 2. Start the backend

```bash
./backend/run.sh
```

This prints the address phones should use (for example `http://192.168.1.20:8000`)
and serves the API on port 8000. Leave it running.

Equivalent manual command:

```bash
conda activate a-mbl
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Sanity check from the Mac: open <http://127.0.0.1:8000/v1/health> — you should
see `"status":"ok"`. Interactive API docs are at <http://127.0.0.1:8000/docs>.

### On Windows

From PowerShell in the repository root, run `.\backend\run.ps1` instead of
`run.sh`. It prints the addresses phones can try (skipping loopback, 169.254.x
and Hyper-V/WSL/VirtualBox adapters), warns when there is no "a-mbl API"
firewall rule (Windows Firewall blocks inbound port 8000 by default; the
warning prints the `New-NetFirewallRule` command to run once in an
Administrator PowerShell), and starts uvicorn from the repository's `.venv` if
it exists, otherwise from the `a-mbl` conda env. Without either it prints how
to create the `.venv`:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Screenshot OCR finds Tesseract on `PATH` or in the Windows installer's default
folders (`%LOCALAPPDATA%\Programs\Tesseract-OCR`, `%ProgramFiles%\Tesseract-OCR`,
`%ProgramFiles(x86)%\Tesseract-OCR`), so a standard install needs no PATH change.

### Trained classifier

On the development Mac the model is already trained: `ml/artifacts/model.joblib`
is present, so `/v1/health` reports `"modelVersion":"tfidf-logreg-0.2.0"`. The
folder is gitignored, so on any other machine (or a fresh clone) the API
classifies with the lexicon baseline alone and `/v1/health` reports
`"modelVersion":"lexicon-0.1.0"`. The hybrid classifier switches on when
`ml/artifacts/model.joblib` exists at backend start. Either copy that file from
a machine that trained it, or train it here: put the Jigsaw Toxic Comment
`train.csv` in `ml/data/` — from the Hugging Face mirror, which needs no
account
(<https://huggingface.co/datasets/thesofakillers/jigsaw-toxic-comment-classification-challenge>,
the copy used on the Mac), or from Kaggle — then

```bash
conda activate a-mbl
pip install -r ml/requirements.txt      # pandas + matplotlib for training
python ml/train.py                      # a few minutes; writes model.joblib, metrics.json, confusion_matrix.png
```

Restart the backend; `/v1/health` then reports the artifact's version (for
example `tfidf-logreg-0.2.0`). `A_MBL_MODEL_PATH=/path/to/model.joblib` loads
the file from elsewhere, and `A_MBL_FORCE_LEXICON=1` keeps the lexicon even
when the file is present. A file that fails to load prints
`[classifier] could not load …` and the API keeps running on the lexicon.
Details and the measured results: [ml/README.md](../ml/README.md).

### Email alerts (optional)

When an alert-eligible case is flagged, the API emails the linked guardians or
school administrators — but only if an SMTP mailbox is configured before the
backend starts. With nothing configured, nothing is sent and in-app alerts
still work. Emails carry the severity, the category, and the involved person's
display name — never any message content. The case owner is never emailed.
An email goes out only when a new alert row is created for that recipient and
case (alert rows are unique per recipient + case), so a repeated share
attempt does not re-send; an unshare deletes that school's alert rows for
the case, so sharing again after an unshare does email again. Sending happens in the
background; a failed send is logged as `[emailer] could not send alert …`
and never fails the request.

```bash
export A_MBL_SMTP_HOST=smtp.gmail.com      # required
export A_MBL_SMTP_FROM=you@example.com     # required
export A_MBL_SMTP_USER=you@example.com     # if the server needs a login
export A_MBL_SMTP_PASSWORD="app password"  # for Gmail: an app password
# A_MBL_SMTP_PORT defaults to 587 with STARTTLS on
# (A_MBL_SMTP_STARTTLS=0 turns STARTTLS off; only for a local test relay)
```

On Windows PowerShell use `$env:A_MBL_SMTP_HOST = "smtp.gmail.com"` (and so on)
in the same window that runs `backend\run.ps1`.

## 3. Start the mobile app

```bash
cd mobile
npx expo start
```

Scan the QR code with **Expo Go** (Android: inside the Expo Go app; iPhone:
with the Camera app). On the first screen, enter the server address printed by
`run.sh` and tap **Check connection** — a green "Connected ✓" card confirms
everything. To pre-fill the address during development, start the bundler with
`EXPO_PUBLIC_API_URL=http://<mac-ip>:8000 npx expo start`.

For step-by-step device testing — your own phone in Expo Go, building the
installable Android APK, or running a remote session for a client — see
[DEVICE_TESTING.md](DEVICE_TESTING.md).

## 4. Demo data (optional but recommended)

```bash
conda activate a-mbl
python -m backend.scripts.seed_demo
```

Synthetic accounts, all with password `demo-pass-123`:

| Email | Role | Notes |
| --- | --- | --- |
| `demo.user@a-mbl.test` | User (adult) | Has sample cases of every severity (caution, high, critical) |
| `demo.guardian@a-mbl.test` | Guardian | Linked to the teen; has an alert |
| `demo.teen@a-mbl.test` | User (13–17) | Activated through the guardian link |
| `demo.admin@a-mbl.test` | School admin | "Demo High School" organization |

School administrator accounts are invitation-only and created from the Mac:

```bash
python -m backend.scripts.create_admin "School name" admin@school.test "a-strong-password" "Display Name"
```

## 5. Tests and checks

```bash
# Backend test suite — 120 tests. With Tesseract installed: 119 passed, 1 skipped
# (the "Tesseract missing" path). Without it, the 6 real-OCR tests skip instead.
# The suite pins the lexicon baseline (A_MBL_FORCE_LEXICON=1) and clears any
# A_MBL_SMTP_* settings, so model.joblib and a real mailbox never affect it.
conda activate a-mbl
python -m pytest backend/tests

# Mobile import-casing check + typecheck, lint, dependency check, and bundle check
cd mobile
npm run check          # scripts/check-casing.mjs, then tsc --noEmit
npm run lint
npx expo-doctor
npx expo export --platform android --output-dir /tmp/ambl-export

# Installable Android APK (writes dist/a-mbl-0.2.0.apk at the repository root)
npm run build:apk
```

## 6. Troubleshooting

| Symptom | Fix |
| --- | --- |
| App says the server is unreachable | Phone and Mac must be on the **same Wi-Fi**. Hotspots and guest networks often isolate devices. |
| Connection worked yesterday, fails today | The Mac's IP changed. Re-run `./backend/run.sh` to see the new address and update it on the app's connection screen (Profile → Change server address). |
| macOS asks about incoming connections | Allow them for Python/uvicorn (System Settings → Network → Firewall). |
| Phone times out against a Windows PC | Windows Firewall blocks inbound port 8000 by default. Once, in an Administrator PowerShell: `New-NetFirewallRule -DisplayName "a-mbl API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow` (`run.ps1` prints this when the rule is missing). |
| `/v1/health` still says `lexicon-0.1.0` after training | `model.joblib` must be in `ml/artifacts/` (or at `A_MBL_MODEL_PATH`), `A_MBL_FORCE_LEXICON` must not be `1`, and the backend must be restarted. Check its log for `[classifier] could not load …`. |
| `Address already in use` on port 8000 | Another server is running: `pkill -f "uvicorn backend.app.main"` and start again. |
| Screenshot scan button says OCR unavailable | `conda install -n a-mbl -c conda-forge tesseract`, then restart the backend. The health check will report `ocrReady: true`. |
| Want a completely fresh start | Stop the backend and delete `backend/data/` (database, keys, evidence — all local demo data), then reseed. |
| Expo Go shows an old version of the app | Shake the device → Reload, or restart `npx expo start` with `-c` to clear the cache. |

## Safety reminder

This is a local HTTP prototype for **synthetic demonstration content only**.
Do not use real sensitive or minor-related conversations. See the limitations
sections in [README.md](../README.md) and [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md).
