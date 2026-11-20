#!/bin/bash
# Download everything the native Android build needs into android/deps
# (skipping what is already there) and set up the host Python venv with sip.
#   deps/qt/<ver>/{android_arm64_v8a,<host>}  Qt for Android and its host tools
#   deps/python-android-<ver>                 Anki's Python for Android (tools/build_python.sh)
#   deps/anki                                 Anki source (for rsbridge)
#   deps/sdist/*                              PyQt6, PyQt6-sip, orjson, rpds-py, markupsafe
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
DEPS=$ROOT/deps
mkdir -p "$DEPS/sdist"
cd "$DEPS"

if [ "$(uname)" = Darwin ]; then
    HOST_OS=mac; HOST_ARCH=clang_64; HOST_DIR=macos; HOST_ICU=
else
    # Linux Qt links against its own ICU 73, a separate archive
    HOST_OS=linux; HOST_ARCH=linux_gcc_64; HOST_DIR=gcc_64; HOST_ICU=icu
fi

venv_python=$("$ROOT/.venv/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)
if [ ! -x "$ROOT/.venv/bin/sip-build" ] || [ "$venv_python" != "$PYTHON_VERSION" ]; then
    uv venv -q --clear -p "$PYTHON_VERSION" "$ROOT/.venv"
    uv pip install -q -p "$ROOT/.venv/bin/python" pip \
        "sip==$SIP_VERSION" "pyqt-builder==$PYQT_BUILDER_VERSION"
fi

QT=$DEPS/qt/$QT_VERSION
if [ ! -d "$QT/$HOST_DIR/bin" ]; then
    uvx --from aqtinstall aqt install-qt "$HOST_OS" desktop "$QT_VERSION" "$HOST_ARCH" \
        --archives qtbase qtsvg qttools $HOST_ICU -O qt -b "$QT_MIRROR"
fi
if [ ! -d "$QT/android_arm64_v8a/lib" ]; then
    uvx --from aqtinstall aqt install-qt all_os android "$QT_VERSION" android_arm64_v8a \
        --archives qtbase qtsvg -O qt -b "$QT_MIRROR"
fi
# aqtinstall writes a host path relative to its working directory
for tool in qmake qmake6; do
    sed -i.bak -E "s|^[^ ]*/bin/qmake6 |$QT/$HOST_DIR/bin/qmake6 |" "$QT/android_arm64_v8a/bin/$tool"
    rm -f "$QT/android_arm64_v8a/bin/$tool.bak"
done

"$ROOT/tools/build_python.sh"

# Anki at ANKI_TAG with shared/patches/ applied; Kioku runs its sync server
# on a thread it can stop and start again (Preferences > Advanced)
"$ROOT/../shared/tools/anki_source.sh" "$DEPS/anki"

sdist() {  # sdist <pypi name> <version> <unpacked dir>
    [ -d "sdist/$3" ] && return
    url=$(curl -fsSL "https://pypi.org/pypi/$1/$2/json" | python3 -c \
        "import json,sys; print(next(u['url'] for u in json.load(sys.stdin)['urls'] if u['packagetype']=='sdist'))")
    curl -fsSL "$url" | tar xz -C sdist
}
sdist pyqt6 "$PYQT6_VERSION" "pyqt6-$PYQT6_VERSION"
sdist pyqt6-sip "$PYQT6_SIP_VERSION" "pyqt6_sip-$PYQT6_SIP_VERSION"
sdist orjson "$ORJSON_VERSION" "orjson-$ORJSON_VERSION"
sdist rpds-py "$RPDS_VERSION" "rpds_py-$RPDS_VERSION"
sdist markupsafe "$MARKUPSAFE_VERSION" "markupsafe-$MARKUPSAFE_VERSION"

# orjson's build.rs turns on its AVX-512 code by the build machine's arch,
# which breaks the arm64 build on an x86_64 host (CI)
PATCH=$ROOT/patches/orjson-target-arch.patch
if ! patch -R -s -f --dry-run -d "sdist/orjson-$ORJSON_VERSION" -p1 < "$PATCH" > /dev/null; then
    patch -s -d "sdist/orjson-$ORJSON_VERSION" -p1 < "$PATCH"
fi
