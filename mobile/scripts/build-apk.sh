#!/usr/bin/env bash
# Build a standalone Android APK that testers can install directly (no Expo
# Go, no Play Store). Output: dist/a-mbl-<version>.apk at the repository root.
#
# Needs JDK 17 in the a-mbl conda env (conda install -n a-mbl -c conda-forge
# openjdk=17) and the Android SDK (Android Studio installs it); Gradle fetches
# the NDK, CMake and platform packages it is missing on the first build.
set -euo pipefail
cd "$(dirname "$0")/.."

env_prefix="$(conda run -n a-mbl python -c 'import sys; print(sys.prefix)')"
export JAVA_HOME="${JAVA_HOME:-$env_prefix/lib/jvm}"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export PATH="$JAVA_HOME/bin:$PATH"

if [ ! -x "$JAVA_HOME/bin/java" ]; then
  echo "JDK 17 not found. Run: conda install -n a-mbl -c conda-forge openjdk=17" >&2
  exit 1
fi
if [ ! -d "$ANDROID_HOME" ]; then
  echo "Android SDK not found at $ANDROID_HOME (install Android Studio, or set ANDROID_HOME)." >&2
  exit 1
fi

# android/ is generated from app.json and never committed. Prebuild also
# rewrites the "android"/"ios" npm scripts to native-run commands; this
# project develops in Expo Go, so the original package.json is restored.
backup="$(mktemp)"
cp package.json "$backup"
trap 'cp "$backup" package.json; rm -f "$backup"' EXIT   # also when prebuild fails
CI=1 npx expo prebuild --platform android --no-install
cp "$backup" package.json

# Real phones only: 64-bit ARM plus 32-bit ARM for older/budget devices.
(cd android && ./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a,armeabi-v7a)

version="$(node -p "require('./app.json').expo.version")"
mkdir -p ../dist
cp android/app/build/outputs/apk/release/app-release.apk "../dist/a-mbl-$version.apk"
echo "APK ready: dist/a-mbl-$version.apk"
