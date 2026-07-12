# Testing a-mbl on real phones

Two situations, two setups:

1. **You, on your own Android phone** — same Wi-Fi as the Mac. Five minutes.
2. **Your client, on her iPhone, anywhere** — the app UI *and* the backend
   both have to reach her, so this needs a tunnel (free) or TestFlight (paid).

## 0. One-time prerequisites on the Mac

| Tool | Check | Install if missing |
| --- | --- | --- |
| Node.js + npm | `node --version` | `brew install node` |
| Conda env `a-mbl` with backend deps | `conda run -n a-mbl python -c "import fastapi"` | see [HOW_TO_RUN.md](HOW_TO_RUN.md) §1 |
| Mobile JS deps | `ls mobile/node_modules` | `cd mobile && npm install` |

(All three were set up on this Mac on 2026-07-12: Node v26, env `a-mbl` from
conda-forge, and `npm install` in `mobile/`.)

On each test phone: install **Expo Go** (Play Store / App Store) and keep it
updated — Expo Go only runs projects on its current SDK (this app: SDK 57).

## 1. Your Android phone (same Wi-Fi)

```bash
# Terminal 1 — backend (note the http://<mac-ip>:8000 address it prints)
./backend/run.sh

# Optional: demo accounts (password demo-pass-123)
conda run -n a-mbl python -m backend.scripts.seed_demo

# Terminal 2 — mobile bundler
cd mobile
npx expo start
```

On the phone: open **Expo Go → Scan QR code** and scan the QR from Terminal 2.
On the app's first screen, enter the address `run.sh` printed and tap
**Check connection**.

Tip: pre-fill that screen by starting the bundler with
`EXPO_PUBLIC_API_URL=http://<mac-ip>:8000 npx expo start`.

If anything fails, the troubleshooting table in
[HOW_TO_RUN.md](HOW_TO_RUN.md) §6 covers the usual causes (different Wi-Fi,
Mac firewall, changed IP, stale Expo Go cache).

## 2. Your client's iPhone (remote)

Two things must reach her phone: the **app bundle** and the **API on your
Mac**. Pick one of these:

| | Option A — live tunnel session | Option B — published update | Option C — TestFlight |
| --- | --- | --- | --- |
| Cost | free | free | Apple Developer, $99/yr |
| Your Mac during her test | must stay running | only the backend tunnel | only the backend tunnel |
| Feels like | dev preview in Expo Go | dev preview in Expo Go | a real installed app |
| Good for | a guided 30-min session | feedback over a few days | serious client testing |

### Option A — live session over tunnels (recommended first)

```bash
# Terminal 1 — backend
./backend/run.sh

# Terminal 2 — expose the backend over HTTPS (prints a https://….trycloudflare.com URL)
brew install cloudflared
cloudflared tunnel --url http://localhost:8000

# Terminal 3 — mobile bundler over a tunnel (free Expo account, first time only)
cd mobile
npx expo login
npx expo start --tunnel
```

Send her two things:

1. The **project link/QR** that `expo start --tunnel` shows (photo of the QR
   is fine — iPhone Camera app opens it in Expo Go).
2. The **`https://….trycloudflare.com` URL** from Terminal 2 — she pastes it
   on the app's *Connect* screen and taps **Check connection**.

Both URLs change every time you restart the tunnels, so send fresh ones per
session.

### Option B — publish the bundle with EAS Update

Publishing puts the JS bundle on Expo's servers so she can open the app in
Expo Go without your bundler running (the backend tunnel from Option A must
still be up while she tests). One-time setup adds the `expo-updates` package
and an EAS project id to the repo:

```bash
cd mobile
npx eas-cli update:configure     # one time — this modifies package.json/app.json
npx eas-cli update --branch preview --message "client test"
```

Share the update link it prints; she opens it on the iPhone and it launches
in Expo Go.

### Option C — TestFlight (a real install on her phone)

Needs an [Apple Developer Program](https://developer.apple.com/programs/)
membership on your Apple ID.

```bash
cd mobile
npx eas-cli build --platform ios --profile production
npx eas-cli submit --platform ios
```

Then in App Store Connect → your app → **TestFlight**, add her email as a
tester; she gets an invite in the TestFlight app.

**Important:** outside Expo Go, iOS blocks plain `http://` addresses (App
Transport Security). A standalone build can only talk to an **https** backend
— the `cloudflared` URL from Option A satisfies this; a bare
`http://<mac-ip>:8000` will not.

## 3. A 2-minute script to send her

1. Open the link I sent — it launches in Expo Go.
2. On *Connect to your local server*, paste the server address I sent and tap
   **Check connection** → you should see "Connected ✓".
3. Create an account (or sign in as `demo.user@a-mbl.test` /
   `demo-pass-123`).
4. On the **Analyze** tab, paste
   `you are such an idiot and a loser, everyone hates you` and tap
   **Analyze** — you should get a High severity result; tap **Open case**.
5. In the case, tap **Reveal** to see the masked preview, and add a review.
6. Check the **Home** tab totals, then poke around — everything is fake data.

## 4. Safety notes for remote testing

- A tunnel makes the API **publicly reachable**: anyone with the URL can
  register and submit text. Use synthetic content only (the app says the
  same), and stop the tunnels (`Ctrl+C`) as soon as the session ends.
- To wipe everything afterwards: stop the backend, `rm -rf backend/data`,
  then reseed. This deletes all accounts, cases, keys, and evidence.
