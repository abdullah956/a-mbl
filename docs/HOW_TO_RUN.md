# How to run a-mbl

Everything runs on your Mac; phones connect over the same Wi-Fi through Expo Go.
Three terminals at most: backend, mobile bundler, and occasional commands.

## 0. Prerequisites (one time)

| Tool | Check | Install if missing |
| --- | --- | --- |
| Conda (miniconda is fine) | `conda --version` | https://docs.conda.io |
| Node.js LTS + npm | `node --version` | https://nodejs.org |
| Expo Go app on each phone | — | App Store / Play Store |
| Tesseract (optional, enables screenshot OCR) | `tesseract --version` | `brew install tesseract` |

## 1. One-time setup

From the repository root:

```bash
# Backend: Python 3.11 environment named a-mbl
conda create -n a-mbl python=3.11 -y
conda activate a-mbl
pip install -r backend/requirements.txt

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

### Email alerts (optional)

When an alert-eligible case is flagged, the API emails the linked guardians or
school administrators — but only if an SMTP mailbox is configured before the
backend starts. With nothing configured, nothing is sent and in-app alerts
still work. Emails carry the severity, the category, and the involved person's
display name — never any message content.

```bash
export A_MBL_SMTP_HOST=smtp.gmail.com      # required
export A_MBL_SMTP_FROM=you@example.com     # required
export A_MBL_SMTP_USER=you@example.com     # if the server needs a login
export A_MBL_SMTP_PASSWORD="app password"  # for Gmail: an app password
# A_MBL_SMTP_PORT defaults to 587 with STARTTLS on
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

For step-by-step device testing — your own Android phone, or sending a build
to someone else's iPhone — see [DEVICE_TESTING.md](DEVICE_TESTING.md).

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
# Backend test suite (87 tests)
conda activate a-mbl
python -m pytest backend/tests

# Mobile typecheck and bundle check
cd mobile
npx tsc --noEmit
npx expo export --platform ios --output-dir /tmp/ambl-export
```

## 6. Troubleshooting

| Symptom | Fix |
| --- | --- |
| App says the server is unreachable | Phone and Mac must be on the **same Wi-Fi**. Hotspots and guest networks often isolate devices. |
| Connection worked yesterday, fails today | The Mac's IP changed. Re-run `./backend/run.sh` to see the new address and update it on the app's connection screen (Profile → Change server address). |
| macOS asks about incoming connections | Allow them for Python/uvicorn (System Settings → Network → Firewall). |
| `Address already in use` on port 8000 | Another server is running: `pkill -f "uvicorn backend.app.main"` and start again. |
| Screenshot scan button says OCR unavailable | `brew install tesseract`, then restart the backend. The health check will report `ocrReady: true`. |
| Want a completely fresh start | Stop the backend and delete `backend/data/` (database, keys, evidence — all local demo data), then reseed. |
| Expo Go shows an old version of the app | Shake the device → Reload, or restart `npx expo start` with `-c` to clear the cache. |

## Safety reminder

This is a local HTTP prototype for **synthetic demonstration content only**.
Do not use real sensitive or minor-related conversations. See the limitations
sections in [README.md](../README.md) and [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md).
