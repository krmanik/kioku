#!/bin/bash
# Host tests for Kioku's Python code (shared/tests) on the build machine:
# desktop Anki's Python packages in a venv, with an rsbridge built from
# android/deps/anki (Anki at ANKI_TAG with shared/patches/ applied). No device
# needed.
# Usage: shared/tests/run.sh [pytest args]
# Env: PYTHON (default python$PYTHON_VERSION from shared/versions.env, Anki's),
#      PROTOC (default: on PATH)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
source "$ROOT/shared/versions.env"
ANKI_SRC=$ROOT/android/deps/anki
WORK=$ROOT/build/host-tests
VENV=$WORK/venv
PYTHON=${PYTHON:-python$PYTHON_VERSION}

"$ROOT/shared/tools/anki_source.sh" "$ANKI_SRC"

venv_python=$("$VENV/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)
if [ "$venv_python" != "$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')" ]; then
    mkdir -p "$WORK"
    "$PYTHON" -m venv --clear "$VENV"
fi
# aqt[qt]: PyQt6 and Qt at the versions the Anki release pins
installed=$("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("aqt"), m.version("pyqt6-qt6"))' 2>/dev/null || true)
if [ "$installed" != "$ANKI_PY_VERSION $QT_VERSION" ]; then
    "$VENV/bin/pip" install -q --resume-retries 10 "anki==$ANKI_PY_VERSION" "aqt[qt]==$ANKI_PY_VERSION" pytest
fi

# rsbridge refuses to load unless its build hash matches the Python package's
mkdir -p "$ANKI_SRC/out"
HASH=$(git -C "$ANKI_SRC" rev-parse --short=8 HEAD)
[ "$(cat "$ANKI_SRC/out/buildhash" 2>/dev/null)" = "$HASH" ] || echo "$HASH" > "$ANKI_SRC/out/buildhash"
export PROTOC=${PROTOC:-$(command -v protoc)}
(cd "$ANKI_SRC" && cargo build -q -p rsbridge --release --features rustls)
# anki is a namespace package (no __init__.py)
SITE=$("$VENV/bin/python" -c "import anki; print(list(anki.__path__)[0])")
LIB=$ANKI_SRC/target/release/librsbridge.$([ "$(uname)" = Darwin ] && echo dylib || echo so)
cp "$LIB" "$SITE/_rsbridge.so"

cd "$ROOT/shared/tests"
exec "$VENV/bin/python" -m pytest -q -p no:cacheprovider "$@"
