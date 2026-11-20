#!/bin/bash
# Build Qt (qtbase + qtsvg) from source for the arm64 iOS Simulator into
# deps/qt/<ver>/iossim. Qt's prebuilt iOS libraries only have arm64 (device)
# and x86_64 (simulator) slices, so Apple silicon simulators need this.
# ios/patches/qios-*.patch are applied to the iOS platform plugin. Skips when
# nothing changed; takes ~20 min on an M-series Mac.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
QT=$ROOT/deps/qt/$QT_VERSION
PREFIX=$QT/iossim
SRC=$ROOT/deps/qt-src-$QT_VERSION
BUILD=$ROOT/build/qt-sim
STAMP=$PREFIX/.kioku

INPUTS=$(cat "$0" "$ROOT/patches/"qios-*.patch | shasum)
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$INPUTS" ]; then
    exit 0
fi

mkdir -p "$SRC"
for module in qtbase qtsvg; do
    [ -d "$SRC/$module" ] || git clone -q --depth 1 --branch "v$QT_VERSION" \
        "https://github.com/qt/$module.git" "$SRC/$module"
done
git -C "$SRC/qtbase" checkout -q -- .
for p in "$ROOT/patches/"qios-*.patch; do
    git -C "$SRC/qtbase" apply "$p"
done

rm -rf "$BUILD" "$PREFIX"
mkdir -p "$BUILD/qtbase" "$BUILD/qtsvg"
LOG=$BUILD/build.log
# Qt 6.11's qyieldcpu.h calls __yield without <arm_acle.h>, which newer
# Xcode clang rejects
NOERR=-Wno-error=implicit-function-declaration
{
    cd "$BUILD/qtbase"
    "$SRC/qtbase/configure" -platform macx-ios-clang -sdk iphonesimulator -release \
        -nomake examples -nomake tests -prefix "$PREFIX" -qt-host-path "$QT/macos" -- \
        -G Ninja -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=17.0 \
        -DCMAKE_C_FLAGS=$NOERR -DCMAKE_CXX_FLAGS=$NOERR \
        -DCMAKE_OBJC_FLAGS=$NOERR -DCMAKE_OBJCXX_FLAGS=$NOERR
    cmake --build . --parallel
    cmake --install .
    cd "$BUILD/qtsvg"
    "$PREFIX/bin/qt-configure-module" "$SRC/qtsvg"
    cmake --build . --parallel
    cmake --install .
} > "$LOG" 2>&1 || {
    grep -E 'error:|FAILED|CMake Error' "$LOG" | head -20
    exit 1
}
echo "$INPUTS" > "$STAMP"
echo "Built $PREFIX"
