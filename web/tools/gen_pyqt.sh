#!/bin/bash
# Generate the PyQt6 binding sources for Qt for WebAssembly from the patched
# sdist copy in deps/, copying only changed files into build/pyqt6-gen so
# ninja rebuilds only those.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$ROOT/deps/emsdk/emsdk_env.sh" >/dev/null 2>&1
SDIST=$ROOT/deps/pyqt6-$PYQT6_VERSION
if [ ! -d "$SDIST" ]; then
    # Qt for WebAssembly lacks QTimeZone's backends, QSystemSemaphore and
    # QNetworkInterface; gate them behind new sip features, disabled below
    rsync -a "$KIOKU_REPO/ios/deps/sdist/pyqt6-$PYQT6_VERSION/" "$SDIST/"
    patch -s -p0 -d "$SDIST" < "$ROOT/patches/pyqt6-wasm.patch"
    python3 "$ROOT/tools/gate_timezone.py" "$SDIST/sip/QtCore/qtimezone.sip"
fi
rm -rf "$ROOT/build/pyqt6-gen.new"
cd "$SDIST"
"$KIOKU_REPO/ios/.venv/bin/sip-build" --no-make --confirm-license --no-tools \
    --no-designer-plugin --no-qml-plugin --no-dbus-python \
    --qmake "$ROOT/deps/qt/$QT_VERSION/wasm_multithread/bin/qmake" \
    --abi-version "$("$KIOKU_REPO/shared/tools/sip_abi.sh" "$KIOKU_REPO/ios/deps/sdist/pyqt6_sip-$PYQT6_SIP_VERSION")" \
    --build-dir "$ROOT/build/pyqt6-gen.new" \
    --enable QtCore --enable QtGui --enable QtWidgets --enable QtNetwork --enable QtSvg \
    --disabled-feature PyQt_DTLS --disabled-feature PyQt_Process \
    --disabled-feature PyQt_Vulkan --disabled-feature PyQt_XCB --disabled-feature PyQt_Wayland \
    --disabled-feature PyQt_SSL --disabled-feature PyQt_TimeZone \
    --disabled-feature PyQt_SystemSemaphore --disabled-feature PyQt_NetworkInterface \
    | grep -v "^Generating"
rsync -rc --delete "$ROOT/build/pyqt6-gen.new/" "$ROOT/build/pyqt6-gen/"
rm -rf "$ROOT/build/pyqt6-gen.new"
"$KIOKU_REPO/ios/.venv/bin/python" "$KIOKU_REPO/shared/tools/gen_pyqt_cmake.py" "$ROOT/build/pyqt6-gen" "$ROOT/build/pyqt6.cmake"
