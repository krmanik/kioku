#!/bin/bash
# Download everything the iOS build needs into ios/deps (skipping what is
# already there) and set up the host Python venv with sip.
#   deps/qt/<ver>/{ios,macos}   Qt for iOS and the macOS host tools it needs
#   deps/python-ios             BeeWare's Python.xcframework
#   deps/anki                   Anki source (for the Rust core, rsbridge)
#   deps/sdist/*                PyQt6, PyQt6-sip, orjson, rpds-py, markupsafe
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
DEPS=$ROOT/deps
mkdir -p "$DEPS/sdist"
cd "$DEPS"

venv_python=$("$ROOT/.venv/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)
if [ ! -x "$ROOT/.venv/bin/sip-build" ] || [ "$venv_python" != "$PYTHON_VERSION" ]; then
    uv venv -q --clear -p "$PYTHON_VERSION" "$ROOT/.venv"
    uv pip install -q -p "$ROOT/.venv/bin/python" pip \
        "sip==$SIP_VERSION" "pyqt-builder==$PYQT_BUILDER_VERSION"
fi

QT=$DEPS/qt/$QT_VERSION
if [ ! -d "$QT/ios/lib/QtSvg.framework" ]; then
    uvx --from aqtinstall aqt install-qt mac desktop "$QT_VERSION" clang_64 \
        --archives qtbase qtsvg -O qt -b "$QT_MIRROR"
    uvx --from aqtinstall aqt install-qt mac ios "$QT_VERSION" ios \
        --archives qtbase qtsvg -O qt -b "$QT_MIRROR"
fi
# point the iOS qmake wrappers at the macOS host Qt (again if deps/ moved)
for tool in qmake qmake6 qtpaths qtpaths6; do
    sed -i '' -E "s|^[^ ]*/bin/(qmake6\|qtpaths6) |$QT/macos/bin/\\1 |" "$QT/ios/bin/$tool"
done
sed -i '' 's|^HostPrefix=.*|HostPrefix=../../macos|; s|^HostData=.*|HostData=.|' \
    "$QT/ios/bin/target_qt.conf"

# Anki's Python (PYTHON_FULL_VERSION); again when versions.env moves
python_ios() { grep -q "^Python version: $PYTHON_FULL_VERSION *$" python-ios/VERSIONS 2>/dev/null; }
if [ ! -d python-ios/Python.xcframework ] || ! python_ios; then
    tag=$PYTHON_APPLE_SUPPORT_TAG
    curl -fsSL -o python-ios.tar.gz \
        "https://github.com/beeware/Python-Apple-support/releases/download/$tag/Python-$PYTHON_VERSION-iOS-support.${tag#*-}.tar.gz"
    rm -rf python-ios
    mkdir -p python-ios && tar xzf python-ios.tar.gz -C python-ios && rm python-ios.tar.gz
    python_ios || { echo "BeeWare $tag is not Python $PYTHON_FULL_VERSION (shared/versions.env):" >&2; head -1 python-ios/VERSIONS >&2; exit 1; }
fi

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

# orjson raised its JSONDecodeError by writing into an unchecked
# PyUnicode_New result: a document too big to copy crashed the app
PATCH=$ROOT/../shared/patches/orjson-loads-error-doc.patch
if ! patch -R -s -f --dry-run -d "sdist/orjson-$ORJSON_VERSION" -p1 < "$PATCH" > /dev/null; then
    patch -s -d "sdist/orjson-$ORJSON_VERSION" -p1 < "$PATCH"
fi

# PyQt6 declares QProcessEnvironment operators outside the PyQt_Process guard,
# which fails once the feature is disabled (iOS has no QProcess)
PATCH=$ROOT/patches/pyqt6-qprocess-guard.patch
if ! patch -R -s -f --dry-run -d "sdist/pyqt6-$PYQT6_VERSION" -p1 < "$PATCH" > /dev/null; then
    patch -s -d "sdist/pyqt6-$PYQT6_VERSION" -p1 < "$PATCH"
fi
