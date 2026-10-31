#!/bin/bash
# Build Kioku for the arm64 iOS Simulator, install it, launch it in dev mode
# (KIOKU_DEV=1) and show its log. The first run builds Qt from source
# (tools/build_qt_sim.sh).
# Usage: run_sim.sh [seconds before reading the log, default 25]
# Env: KIOKU_SIM  simulator name or UDID (default: the first available iPhone)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
SECS=${1:-25}
QT=$ROOT/deps/qt/$QT_VERSION

"$ROOT/tools/fetch_deps.sh"
"$ROOT/tools/build_qt_sim.sh"
"$ROOT/tools/build_rust.sh" aarch64-apple-ios-sim
"$ROOT/tools/gen_pyqt.sh" > /dev/null
"$ROOT/../shared/tools/prepare_site.sh" "$ROOT/.venv/bin/python" "$ROOT/deps/sdist" "$ROOT/build/site"
"$ROOT/../shared/tools/build_pymupdf.sh" ios-sim > "$ROOT/build/pymupdf.log" 2>&1 || {
    tail -30 "$ROOT/build/pymupdf.log"; exit 1; }
rsync -a "$ROOT/../build/pymupdf/ios-sim/site/" "$ROOT/build/site/"
"$ROOT/../shared/tools/build_programs.sh" ios-sim > "$ROOT/build/programs.log" 2>&1 || {
    tail -30 "$ROOT/build/programs.log"; exit 1; }
rsync -a --delete "$ROOT/../build/programs/data/" "$ROOT/build/site/kioku_programs_data/"
# Python packages with native code (numpy, Pillow, cryptography, lxml, ...)
"$ROOT/../shared/tools/build_wheels.sh" ios-sim > "$ROOT/build/wheels.log" 2>&1 || {
    tail -30 "$ROOT/build/wheels.log"; exit 1; }
rsync -a "$ROOT/../build/wheels/ios-sim/site/" "$ROOT/build/site/"

"$QT/iossim/bin/qt-cmake" -S "$ROOT" -B "$ROOT/build/xcode-sim" -G Xcode \
    -DQT_HOST_PATH="$QT/macos" -DCMAKE_OSX_SYSROOT=iphonesimulator \
    -DCMAKE_OSX_ARCHITECTURES=arm64 > /dev/null
cd "$ROOT/build/xcode-sim"
xcodebuild -project Kioku.xcodeproj -target Kioku -configuration Release \
    -sdk iphonesimulator -arch arm64 CODE_SIGN_IDENTITY=- \
    > "$ROOT/build/xcode-sim.log" 2>&1 || {
    grep -E 'error:|^ld: |Undefined' "$ROOT/build/xcode-sim.log" | sort -u | head -40
    exit 1
}
APP=$ROOT/build/xcode-sim/Release-iphonesimulator/Kioku.app
echo "Built $APP"

SIM=${KIOKU_SIM:-$(xcrun simctl list devices available | grep -m1 'iPhone' \
    | grep -oE '[0-9A-F-]{36}')}
xcrun simctl boot "$SIM" 2>/dev/null || true
xcrun simctl install "$SIM" "$APP"
# the simulator sets no USER, which getpass.getuser() (aqt) needs
SIMCTL_CHILD_USER=mobile SIMCTL_CHILD_KIOKU_DEV=1 \
    xcrun simctl launch --terminate-running-process "$SIM" io.ankidesk.kioku > /dev/null
sleep "$SECS"
DATA=$(xcrun simctl get_app_container "$SIM" io.ankidesk.kioku data)
echo "== $DATA/Documents/kioku.log"; tail -60 "$DATA/Documents/kioku.log" 2>/dev/null
