#!/bin/bash
# Build Kioku for a connected iPhone, install it, launch it in dev mode
# (KIOKU_DEV=1, see shared/python/kioku/devtools.py) and show its log.
# Usage: KIOKU_TEAM=<team id> run_device.sh [seconds before reading the log, default 30]
# Env: KIOKU_DEVICE  device id (default: the first connected iPhone)
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SECS=${1:-30}
: "${KIOKU_TEAM:?set KIOKU_TEAM to your Apple development team id}"
DEV=${KIOKU_DEVICE:-$(xcrun devicectl list devices 2>/dev/null | grep physical \
    | grep -oE '[0-9A-F]{8}-[0-9A-F]{16}' | head -1)}
LOGDIR=$ROOT/build/device-logs
mkdir -p "$LOGDIR"
KIOKU_DEV_BUILD=1 "$ROOT/tools/build.sh" > /dev/null || exit 1
xcrun devicectl device install app --device "$DEV" \
    "$ROOT/build/xcode-dev/Release-iphoneos/Kioku.app" > /dev/null || exit 1
xcrun devicectl device process launch --device "$DEV" --terminate-existing \
    --environment-variables '{"KIOKU_DEV": "1"}' \
    io.ankidesk.kioku > "$LOGDIR/console.txt" 2>&1
sleep "$SECS"
xcrun devicectl device copy from --device "$DEV" --domain-type appDataContainer \
    --domain-identifier io.ankidesk.kioku --source Documents/kioku.log \
    --destination "$LOGDIR/kioku.log" > /dev/null 2>&1
echo "== kioku.log"; tail -60 "$LOGDIR/kioku.log" 2>/dev/null
