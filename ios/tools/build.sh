#!/bin/bash
# Build Kioku for iOS devices from a clean checkout:
# dependencies → Rust core → PyQt6 sources → site-packages → Xcode build.
#
#   KIOKU_TEAM=<Apple team id> tools/build.sh   signed build for your devices
#   tools/build.sh                              unsigned; also writes
#                                               build/Kioku-<version>-unsigned.ipa
#                                               for sideloading tools to re-sign
# Env: KIOKU_VERSION, KIOKU_BUILD (default: Anki's version, 1)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
VERSION=${KIOKU_VERSION:-$ANKI_PY_VERSION}
BUILD_NUMBER=${KIOKU_BUILD:-1}
TEAM=${KIOKU_TEAM:-}
QT=$ROOT/deps/qt/$QT_VERSION

"$ROOT/tools/fetch_deps.sh"
"$ROOT/tools/build_qt_plugin.sh"
"$ROOT/tools/build_rust.sh" aarch64-apple-ios
"$ROOT/tools/gen_pyqt.sh" > /dev/null
"$ROOT/../shared/tools/prepare_site.sh" "$ROOT/.venv/bin/python" "$ROOT/deps/sdist" "$ROOT/build/site"
"$ROOT/../shared/tools/build_pymupdf.sh" ios > "$ROOT/build/pymupdf.log" 2>&1 || {
    tail -30 "$ROOT/build/pymupdf.log"; exit 1; }
cp -R "$ROOT/../build/pymupdf/ios/site/" "$ROOT/build/site/"
"$ROOT/../shared/tools/build_programs.sh" ios > "$ROOT/build/programs.log" 2>&1 || {
    tail -30 "$ROOT/build/programs.log"; exit 1; }
rsync -a --delete "$ROOT/../build/programs/data/" "$ROOT/build/site/kioku_programs_data/"
# Python packages with native code (numpy, Pillow, cryptography, lxml, ...)
"$ROOT/../shared/tools/build_wheels.sh" ios > "$ROOT/build/wheels.log" 2>&1 || {
    tail -30 "$ROOT/build/wheels.log"; exit 1; }
rsync -a "$ROOT/../build/wheels/ios/site/" "$ROOT/build/site/"

"$QT/ios/bin/qt-cmake" -S "$ROOT" -B "$ROOT/build/xcode-dev" -G Xcode \
    -DQT_HOST_PATH="$QT/macos" -DCMAKE_OSX_SYSROOT=iphoneos -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DKIOKU_TEAM="$TEAM" -DKIOKU_VERSION="$VERSION" -DKIOKU_BUILD="$BUILD_NUMBER" > /dev/null

cd "$ROOT/build/xcode-dev"
if [ -n "$TEAM" ]; then
    SIGNING=(-allowProvisioningUpdates)
else
    SIGNING=(CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY=)
fi
xcodebuild -project Kioku.xcodeproj -target Kioku -configuration Release \
    -sdk iphoneos -arch arm64 "${SIGNING[@]}" > "$ROOT/build/xcode-dev.log" 2>&1 || {
    grep -E 'error:|^ld: |Undefined' "$ROOT/build/xcode-dev.log" | sort -u | head -40
    exit 1
}
APP=$ROOT/build/xcode-dev/Release-iphoneos/Kioku.app
echo "Built $APP"

if [ -z "$TEAM" ]; then
    rm -rf "$ROOT/build/ipa" && mkdir -p "$ROOT/build/ipa/Payload"
    cp -R "$APP" "$ROOT/build/ipa/Payload/"
    IPA=$ROOT/build/Kioku-$VERSION-unsigned.ipa
    (cd "$ROOT/build/ipa" && rm -f "$IPA" && zip -qry "$IPA" Payload)
    echo "Packaged $IPA"
fi
