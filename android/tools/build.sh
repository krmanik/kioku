#!/bin/bash
# Build Kioku for Android (arm64-v8a) from a clean checkout:
# dependencies → patched Qt platform plugin → Rust core → PyQt6 sources →
# site-packages → python.zip → Qt/Gradle build. Writes
# build/Kioku-<version>.apk (debug-signed).
# Env: ANDROID_SDK_ROOT (default ~/Library/Android/sdk), ANDROID_NDK_ROOT
#      (default the SDK's NDK 28.2), JAVA_HOME (default Android Studio's JDK),
#      KIOKU_VERSION, KIOKU_BUILD (default: Anki's version, 1),
#      KIOKU_KEYSTORE, KIOKU_KEYSTORE_PASSWORD, KIOKU_KEY_ALIAS,
#      KIOKU_KEY_PASSWORD (default: the debug key),
#      KIOKU_DEV_BUILD=1 (allow the dev command channel; run_device.sh sets it)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
VERSION=${KIOKU_VERSION:-$ANKI_PY_VERSION}
BUILD_NUMBER=${KIOKU_BUILD:-1}
export ANDROID_SDK_ROOT=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}
export ANDROID_NDK_ROOT=${ANDROID_NDK_ROOT:-$ANDROID_SDK_ROOT/ndk/28.2.13676358}
STUDIO_JDK="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
if [ -z "${JAVA_HOME:-}" ] && [ -d "$STUDIO_JDK" ]; then export JAVA_HOME=$STUDIO_JDK; fi
# Gradle's downloads time out over IPv6 on some networks
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Djava.net.preferIPv4Stack=true"
QT=$ROOT/deps/qt/$QT_VERSION
HOST_DIR=$( [ "$(uname)" = Darwin ] && echo macos || echo gcc_64 )
BUILD=$ROOT/build/cmake

"$ROOT/tools/fetch_deps.sh"
"$ROOT/tools/build_qt_plugin.sh"
"$ROOT/tools/build_rust.sh"
"$ROOT/tools/gen_pyqt.sh" > /dev/null
"$ROOT/../shared/tools/prepare_site.sh" "$ROOT/.venv/bin/python" "$ROOT/deps/sdist" "$ROOT/build/site"
# PyMuPDF: its modules sit next to libmupdfcpp.so (RUNPATH $ORIGIN) and are
# unpacked with the rest of the runtime
"$ROOT/../shared/tools/build_pymupdf.sh" android > "$ROOT/build/pymupdf.log" 2>&1 || {
    tail -30 "$ROOT/build/pymupdf.log"; exit 1; }
rsync -a "$ROOT/../build/pymupdf/android/site/" "$ROOT/build/site/"
# the programs add-ons start (ffmpeg, mecab, ...): libkiokuprog.so, an extra
# native library (CMakeLists.txt)
"$ROOT/../shared/tools/build_programs.sh" android > "$ROOT/build/programs.log" 2>&1 || {
    tail -30 "$ROOT/build/programs.log"; exit 1; }
rsync -a --delete "$ROOT/../build/programs/data/" "$ROOT/build/site/kioku_programs_data/"
# Python packages with native code (numpy, Pillow, cryptography, lxml, ...)
"$ROOT/../shared/tools/build_wheels.sh" android > "$ROOT/build/wheels.log" 2>&1 || {
    tail -30 "$ROOT/build/wheels.log"; exit 1; }
rsync -a "$ROOT/../build/wheels/android/site/" "$ROOT/build/site/"

# package/ plus the Python runtime as an asset
mkdir -p "$BUILD/package"
rsync -a --delete --exclude assets "$ROOT/package/" "$BUILD/package/"
"$ROOT/tools/pack_python.sh" "$ROOT/build/site" "$BUILD/package/assets/python.zip"

"$QT/android_arm64_v8a/bin/qt-cmake" -S "$ROOT" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DQT_HOST_PATH="$QT/$HOST_DIR" \
    -DANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" -DANDROID_NDK_ROOT="$ANDROID_NDK_ROOT" \
    -DKIOKU_VERSION="$VERSION" -DKIOKU_BUILD="$BUILD_NUMBER" > "$ROOT/build/cmake.log"
cmake --build "$BUILD" --target apk > "$ROOT/build/build.log" 2>&1 || {
    grep -E 'error:|FAILED|undefined symbol|Exception|What went wrong' -A3 "$ROOT/build/build.log" \
        | head -60
    exit 1
}
APK=$(find "$BUILD/android-build" -name '*.apk' -newer "$ROOT/build/cmake.log" | head -1)
# Gradle's release APK is unsigned: sign it with KIOKU_KEYSTORE (release key,
# see .github/workflows/android.yml) or the debug key
KEYSTORE=${KIOKU_KEYSTORE:-$HOME/.android/debug.keystore}
STORE_PASS=${KIOKU_KEYSTORE_PASSWORD:-android}
KEY_ALIAS=${KIOKU_KEY_ALIAS:-androiddebugkey}
KEY_PASS=${KIOKU_KEY_PASSWORD:-$STORE_PASS}
if [ ! -f "$KEYSTORE" ]; then
    mkdir -p "$(dirname "$KEYSTORE")"
    "$JAVA_HOME/bin/keytool" -genkeypair -keystore "$KEYSTORE" -storepass android \
        -alias androiddebugkey -keypass android -keyalg RSA -validity 10000 \
        -dname "CN=Android Debug,O=Android,C=US" > /dev/null
fi
BUILD_TOOLS=$(ls -d "$ANDROID_SDK_ROOT"/build-tools/* | sort -V | tail -1)
"$BUILD_TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-pass "pass:$STORE_PASS" \
    --ks-key-alias "$KEY_ALIAS" --key-pass "pass:$KEY_PASS" \
    --out "$ROOT/build/Kioku-$VERSION.apk" "$APK"
echo "Built $ROOT/build/Kioku-$VERSION.apk"
