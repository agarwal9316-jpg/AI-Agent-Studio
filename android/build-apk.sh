#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
if [[ ! -x "$JAVA_HOME/bin/java" ]]; then
  if command -v java >/dev/null 2>&1; then
    export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")"
  fi
fi
export ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/workspace/android-sdk}}"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
if [[ ! -f local.properties ]]; then
  echo "sdk.dir=$ANDROID_HOME" > local.properties
fi
VERSION_NAME="1.27.86"
chmod +x ./gradlew
./gradlew assembleDebug --no-daemon
mkdir -p dist
cp -f app/build/outputs/apk/debug/app-debug.apk "dist/AI-Agent-Studio-${VERSION_NAME}-debug.apk"
echo "Built: $ROOT/dist/AI-Agent-Studio-${VERSION_NAME}-debug.apk"
ls -lh dist/
