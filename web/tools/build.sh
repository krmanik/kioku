#!/bin/bash
# Configure (once) and build kioku.wasm with the app page (build/cmake).
# The app's Python (python/, Kioku's shared/python) and shell/ are packed
# by tools/pack_app.sh on every build without relinking: seconds instead of
# minutes. The stdlib and site-packages (kioku.data) are packed at link time.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$ROOT/deps/emsdk/emsdk_env.sh" >/dev/null 2>&1
QT=$ROOT/deps/qt/$QT_VERSION
"$KIOKU_REPO/shared/tools/cmake_fresh.sh" "$ROOT/build/cmake" "$QT/wasm_multithread"
if [ ! -f "$ROOT/build/cmake/CMakeCache.txt" ]; then
    "$QT/wasm_multithread/bin/qt-cmake" -S "$ROOT" -B "$ROOT/build/cmake" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release -DQT_HOST_PATH="$QT/macos" \
        -DKIOKU_REPO="$KIOKU_REPO" -DKIOKU_ASYNCIFY=ON
fi
ninja -C "$ROOT/build/cmake"
