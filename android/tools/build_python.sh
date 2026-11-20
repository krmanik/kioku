#!/bin/bash
# Build Anki's Python (PYTHON_FULL_VERSION) for Android into
# deps/python-android-<version>/prefix. python.org ships Android builds only
# from 3.14 (Chaquopy stops at 3.13.16), so build it from the CPython source
# with its own Android/android.py, the script python.org's packages are made
# with. The copy keeps what `android.py package` keeps (package itself needs
# a git checkout): headers, libpython, the standard library, and OpenSSL and
# SQLite as libssl_python.so etc.
# Env: ANDROID_HOME (default ANDROID_SDK_ROOT or ~/Library/Android/sdk);
# android-env.sh installs the NDK CPython pins if it is missing.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
export ANDROID_HOME=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}
HOST=aarch64-linux-android
SRC=$ROOT/deps/Python-$PYTHON_FULL_VERSION
OUT=$ROOT/deps/python-android-$PYTHON_FULL_VERSION
[ -f "$OUT/prefix/lib/libpython$PYTHON_VERSION.so" ] && exit 0

if [ ! -d "$SRC" ]; then
    curl -fsSL "https://www.python.org/ftp/python/$PYTHON_FULL_VERSION/Python-$PYTHON_FULL_VERSION.tgz" \
        | tar xz -C "$ROOT/deps"
fi
# the NDK CPython builds with (android-env.sh looks for sdkmanager only in
# cmdline-tools/latest)
ndk_version=$(sed -n 's/^ndk_version=//p' "$SRC/Android/android-env.sh")
if [ ! -f "$ANDROID_HOME/ndk/$ndk_version/package.xml" ]; then
    SDKMANAGER=$(command -v sdkmanager || echo "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager")
    # yes ends on SIGPIPE when sdkmanager is done (pipefail)
    { yes || true; } | "$SDKMANAGER" "ndk;$ndk_version" > /dev/null
fi
# the build machine's Python first (cross-compiling runs it), then arm64
python3 "$SRC/Android/android.py" build build
python3 "$SRC/Android/android.py" build "$HOST"

STRIP=$(echo "$ANDROID_HOME/ndk/$ndk_version"/toolchains/llvm/prebuilt/*/bin/llvm-strip)
STAGE=$OUT.partial
rm -rf "$STAGE"
cd "$SRC/cross-build/$HOST/prefix"
for path in include/openssl* include/python* include/sqlite* \
        lib/engines-3 lib/libcrypto*.so lib/libpython* lib/libsqlite* lib/libssl*.so \
        lib/ossl-modules lib/python* \
        lib/pkgconfig/*crypto* lib/pkgconfig/*ssl* lib/pkgconfig/*python* lib/pkgconfig/*sqlite*; do
    [ -e "$path" ] || continue
    mkdir -p "$STAGE/prefix/$(dirname "$path")"
    cp -a "$path" "$STAGE/prefix/$path"
done
find "$STAGE" -name __pycache__ -prune -exec rm -rf {} +
find "$STAGE" -name '*.so' -type f -exec "$STRIP" {} +
mv "$STAGE" "$OUT"
