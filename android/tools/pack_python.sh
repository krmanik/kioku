#!/bin/bash
# Pack the Python runtime that KiokuActivity unpacks on the first start:
#   lib/python3.14/  the standard library with lib-dynload (python.org's build)
#   app/             the shared kioku package and PyQt6 overlay + the Android layer
#   app_packages/    Anki and its dependencies (shared/tools/prepare_site.sh)
#   dev-build        only with KIOKU_DEV_BUILD=1: allows the dev command channel
#                    (shared/python/kioku/devtools.py); release builds leave it out
# Usage: pack_python.sh <site dir> <output zip>
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
SITE=$1
OUT=$2
PREFIX=$ROOT/deps/python-android/prefix
STAGE=$ROOT/build/python-stage
# test-only modules and stubs; the extra files for add-ons are downloaded
# (shared/tools/packs.py, kioku/packs.py)
PACK_EXCLUDES=$(mktemp)
trap 'rm -f "$PACK_EXCLUDES"' EXIT
python3 "$ROOT/../shared/tools/packs.py" excludes > "$PACK_EXCLUDES"
EXCLUDES=(--exclude '__pycache__' --exclude '*.pyc'
    --exclude-from="$ROOT/../shared/tools/bundle_excludes.txt")

mkdir -p "$STAGE/lib"
rsync -a --delete --delete-excluded "${EXCLUDES[@]}" \
    --exclude 'test/' --exclude 'idlelib/' --exclude 'tkinter/' \
    --exclude 'turtledemo/' --exclude 'ensurepip/' --exclude 'config-*/' \
    "$PREFIX/lib/python$PYTHON_VERSION/" "$STAGE/lib/python$PYTHON_VERSION/"
rsync -a --delete "${EXCLUDES[@]}" "$ROOT/../shared/python/" "$STAGE/app/"
rsync -a "${EXCLUDES[@]}" "$ROOT/python/" "$STAGE/app/"
rsync -a --delete --delete-excluded "${EXCLUDES[@]}" --exclude-from="$PACK_EXCLUDES" "$SITE/" "$STAGE/app_packages/"

# extension modules from wheels keep their symbol tables; the dynamic symbols
# (PyInit_*) stay
STRIP=$(ls "${ANDROID_NDK_ROOT:-}"/toolchains/llvm/prebuilt/*/bin/llvm-strip 2>/dev/null | head -1)
if [ -n "$STRIP" ]; then
    find "$STAGE" -name '*.so' -exec "$STRIP" --strip-unneeded {} +
fi

rm -f "$STAGE/dev-build"
if [ "${KIOKU_DEV_BUILD:-}" = 1 ]; then touch "$STAGE/dev-build"; fi

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
(cd "$STAGE" && zip -qr -X "$OUT" lib app app_packages $(ls dev-build 2>/dev/null))
echo "Packed $OUT ($(du -h "$OUT" | cut -f1))"
