#!/bin/bash
# Build Kioku, install it on the connected device or emulator, launch it in
# dev mode (KIOKU_DEV=1, see shared/python/kioku/devtools.py) and show its log.
# Usage: run_device.sh [seconds before reading the log, default 30]
# Env: ANDROID_SERIAL  device to use (default: the only connected one)
#      KIOKU_NO_BUILD=1  install the last build
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
SECS=${1:-30}
ADB=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}/platform-tools/adb
APP=io.ankidesk.kioku
DOCS=/sdcard/Android/data/$APP/files
LOGDIR=$ROOT/build/device-logs
mkdir -p "$LOGDIR"
if [ -z "${KIOKU_NO_BUILD:-}" ]; then
    KIOKU_DEV_BUILD=1 "$ROOT/tools/build.sh" || exit 1
fi
"$ADB" install -r "$ROOT/build/Kioku-${KIOKU_VERSION:-$ANKI_PY_VERSION}.apk" > /dev/null || exit 1
"$ADB" logcat -c
"$ADB" shell am force-stop $APP
"$ADB" shell "mkdir -p $DOCS && touch $DOCS/.kioku-dev"
# the app icon's intent: started with another one, a later tap on the icon
# could start a second activity (KiokuLinkActivity.java)
"$ADB" shell am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER \
    -n $APP/.KiokuActivity --ez dev true > /dev/null
sleep "$SECS"
"$ADB" logcat -d -v brief > "$LOGDIR/logcat.txt"
"$ADB" pull $DOCS/kioku.log "$LOGDIR/kioku.log" > /dev/null 2>&1
echo "== logcat (Kioku, Python, crashes)"
grep -E 'Kioku|python|AndroidRuntime|DEBUG|libc|Qt' "$LOGDIR/logcat.txt" | tail -40
echo "== kioku.log"; tail -60 "$LOGDIR/kioku.log" 2>/dev/null
