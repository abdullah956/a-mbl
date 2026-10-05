# a-mbl mobile app

Expo (SDK 57) + React Native + TypeScript + Expo Router client for the local
a-mbl backend. See the repository root README for the full picture.

## Run (development, Expo Go)

```bash
npm install
npx expo start
```

Scan the QR code with **Expo Go** (Android or iPhone). The phone and the Mac
must be on the same Wi-Fi. On first launch the app asks for the server
address — start the backend with `../backend/run.sh`, which prints it.

## Build an installable Android APK

```bash
npm run build:apk     # → ../dist/a-mbl-<version>.apk
```

`scripts/build-apk.sh` regenerates `android/` from `app.json` with
`expo prebuild` (the folder is gitignored), then runs Gradle's
`assembleRelease` for arm64-v8a and armeabi-v7a. It needs JDK 17 in the
`a-mbl` conda env and the Android SDK; see
[../docs/DEVICE_TESTING.md](../docs/DEVICE_TESTING.md) §2 for sending the APK
to a tester.

## Structure

```text
src/
├── app/                  # expo-router routes
│   ├── index.tsx         # boot: server → session → role routing
│   ├── connect.tsx       # editable server address + /v1/health check
│   ├── (auth)/           # welcome, age screen, register, login
│   ├── pending.tsx       # 13–17 guardian-approval waiting room
│   ├── (tabs)/           # Home, Analyze, Cases, Alerts, Profile
│   ├── case/[id].tsx     # case detail: reveal, review, share, evidence
│   ├── reports.tsx       # summaries, weekly trend, masked PDF
│   └── members.tsx       # school administrators' member list
├── components/ui.tsx     # small shared UI kit (48pt targets, a11y labels)
└── lib/                  # typed API client, auth context, theme, types, image normalization
assets/images/            # app icon, adaptive icon layers, splash, favicon
scripts/build-apk.sh      # one-command release APK build
```

## Checks

```bash
npx tsc --noEmit     # strict typecheck
npm run lint         # ESLint (eslint-config-expo)
npx expo-doctor      # dependency / config health
npx expo export      # verify the bundle builds
```

Raw analyzed content is never persisted on the device; only the server
address and the refresh token are stored, in SecureStore.
