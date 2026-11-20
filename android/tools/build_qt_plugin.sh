#!/bin/bash
# Rebuild Qt's Android platform plugin with android/patches/qtforandroid-*.patch
# (qtplugin/CMakeLists.txt) and put it in place of the prebuilt one in
# deps/qt, keeping that as deps/qt/<ver>/qtforandroid.orig.so. Skips when
# nothing changed.
# Env: ANDROID_SDK_ROOT, ANDROID_NDK_ROOT (set by build.sh)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
QT=$ROOT/deps/qt/$QT_VERSION
HOST_DIR=$( [ "$(uname)" = Darwin ] && echo macos || echo gcc_64 )
SRC=$ROOT/deps/qtbase-$QT_VERSION
BUILD=$ROOT/build/qtplugin
PLUGIN=$QT/android_arm64_v8a/plugins/platforms/libplugins_platforms_qtforandroid_arm64-v8a.so
ORIG=$QT/qtforandroid.orig.so
STAMP=$QT/qtforandroid.kioku

INPUTS=$(cat "$0" "$ROOT/qtplugin/CMakeLists.txt" "$ROOT/patches/"qtforandroid-*.patch | shasum)
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$INPUTS" ]; then
    exit 0
fi

if [ ! -d "$SRC" ]; then
    git clone -q --depth 1 --branch "v$QT_VERSION" --filter=blob:none --sparse \
        https://github.com/qt/qtbase.git "$SRC"
    git -C "$SRC" sparse-checkout set src/plugins/platforms/android src/3rdparty/android
fi
git -C "$SRC" checkout -q -- .
for p in "$ROOT/patches/"qtforandroid-*.patch; do
    git -C "$SRC" apply "$p"
done

mkdir -p "$ROOT/build"
"$ROOT/../shared/tools/cmake_fresh.sh" "$BUILD" "$QT/android_arm64_v8a"
"$QT/android_arm64_v8a/bin/qt-cmake" -S "$ROOT/qtplugin" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DQT_HOST_PATH="$QT/$HOST_DIR" -DQTBASE_SRC="$SRC" \
    -DANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" -DANDROID_NDK_ROOT="$ANDROID_NDK_ROOT" \
    > "$ROOT/build/qtplugin-cmake.log"
cmake --build "$BUILD" > "$ROOT/build/qtplugin-build.log" 2>&1 || {
    grep -E 'error:|FAILED|undefined' -A3 "$ROOT/build/qtplugin-build.log" | head -40
    exit 1
}
[ -f "$ORIG" ] || cp "$PLUGIN" "$ORIG"
cp "$BUILD/libplugins_platforms_qtforandroid_arm64-v8a.so" "$PLUGIN"
echo "$INPUTS" > "$STAMP"
echo "Patched $PLUGIN"
