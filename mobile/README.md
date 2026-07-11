# a-mbl mobile app

Expo (SDK 57) + React Native + TypeScript + Expo Router client for the local
a-mbl backend. See the repository root README for the full picture.

## Run

```bash
npm install
npx expo start
```

Scan the QR code with **Expo Go** (Android or iPhone). The phone and the Mac
must be on the same Wi-Fi. On first launch the app asks for the server
address — start the backend with `../backend/run.sh`, which prints it.

## Structure

```text
src/
├── app/                  # expo-router routes
│   ├── index.tsx         # boot: server → session → role routing
│   ├── connect.tsx       # editable server address + /v1/health check
│   ├── (auth)/           # welcome, age screen, register, login
│   ├── pending.tsx       # 13–17 guardian-approval waiting room
│   ├── (tabs)/           # Home, Analyze, Cases, Alerts, Profile
│   └── case/[id].tsx     # case detail: reveal, review, share, evidence
├── components/ui.tsx     # small shared UI kit (44pt targets, a11y labels)
└── lib/                  # typed API client, auth context, theme, types
```

## Checks

```bash
npx tsc --noEmit     # strict typecheck
npx expo export      # verify the bundle builds
```

Raw analyzed content is never persisted on the device; only the refresh token
is stored, in SecureStore.
