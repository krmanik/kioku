#!/bin/bash
# Generate the PyQt6 binding sources for iOS and the CMake fragment that builds them.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
# Regenerating rewrites every source file and forces a full rebuild, so skip
# it when nothing that goes into it changed.
STAMP=$ROOT/build/pyqt6-gen/.inputs
INPUTS=$(cat "$0" "$ROOT/../shared/versions.env" "$ROOT/patches/"*.patch | shasum)
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$INPUTS" ] && [ -f "$ROOT/cmake/pyqt6.cmake" ]; then
    exit 0
fi
cd "$ROOT/deps/sdist/pyqt6-$PYQT6_VERSION"
rm -rf "$ROOT/build/pyqt6-gen"
mkdir -p "$ROOT/cmake" "$ROOT/build"
"$ROOT/.venv/bin/sip-build" --no-make --confirm-license --no-tools \
    --abi-version "$("$ROOT/../shared/tools/sip_abi.sh" "$ROOT/deps/sdist/pyqt6_sip-$PYQT6_SIP_VERSION")" \
    --no-designer-plugin --no-qml-plugin --no-dbus-python \
    --qmake "$ROOT/deps/qt/$QT_VERSION/ios/bin/qmake" \
    --build-dir "$ROOT/build/pyqt6-gen" \
    --enable QtCore --enable QtGui --enable QtWidgets --enable QtNetwork --enable QtSvg \
    --disabled-feature PyQt_DTLS --disabled-feature PyQt_Process \
    --disabled-feature PyQt_Vulkan --disabled-feature PyQt_XCB --disabled-feature PyQt_Wayland \
    "$@"
"$ROOT/.venv/bin/python" "$ROOT/../shared/tools/gen_pyqt_cmake.py" "$ROOT/build/pyqt6-gen" "$ROOT/cmake/pyqt6.cmake"
echo "$INPUTS" > "$STAMP"
