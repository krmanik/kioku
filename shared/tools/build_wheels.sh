#!/bin/bash
# Python packages with native code that add-ons import, for the native apps
# (docs/addon-deps.md): numpy, Pillow, cryptography (with cffi and pyOpenSSL)
# and jieba. Not lxml and psutil: optional in the add-ons that import them, and
# neither builds for these platforms as it is.
#   ios, ios-sim: prebuilt iOS wheels (numpy and cryptography from BeeWare's
#                 index, Pillow from PyPI)
#   android:      all built with cibuildwheel (no Android wheels on PyPI)
# The wheels' .so files are extension modules like the standard library's:
# iOS moves them into frameworks (ios/tools/bundle_python.sh), Android loads
# them from the unpacked runtime.
# Output: build/wheels/<target>/site, unpacked, for the apps' site-packages.
# Usage: build_wheels.sh ios|ios-sim|android
# Env: ANDROID_HOME (android; default ~/Library/Android/sdk)
set -euo pipefail
SHARED=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$SHARED/.." && pwd)
source "$SHARED/versions.env"
TARGET=${1:?ios, ios-sim or android}
WORK=$ROOT/build/wheels
SRC=$WORK/src
WHEELS=$WORK/$TARGET/wheels
SITE=$WORK/$TARGET/site
mkdir -p "$SRC" "$WHEELS"
export ANDROID_HOME=${ANDROID_HOME:-$HOME/Library/Android/sdk}
PY=${PYTHON_VERSION/./}

case $TARGET in
ios) PLATFORM=ios; TAG=arm64_iphoneos; CIBW=cp$PY-ios_arm64_iphoneos ;;
ios-sim) PLATFORM=ios; TAG=arm64_iphonesimulator; CIBW=cp$PY-ios_arm64_iphonesimulator ;;
android) PLATFORM=android; TAG=android; CIBW=cp$PY-android_arm64_v8a ;;
*) echo "unknown target $TARGET" >&2; exit 1 ;;
esac

# a wheel from a package index (simple API): fetch_wheel <index> <name> <version>
fetch_wheel() {
    ls "$WHEELS"/$2-$3-*.whl > /dev/null 2>&1 && return
    echo "fetching $2 $3"
    local url
    url=$(curl -fsSL "$1/$2/" | python3 -c "
import re, sys, urllib.parse
for href in re.findall(r'href=\"([^\"]+)\"', sys.stdin.read()):
    name = href.split('#')[0].rsplit('/', 1)[-1]
    if name.startswith('$2-$3-') and '$TAG' in name and ('cp$PY' in name or 'abi3' in name):
        print(urllib.parse.urljoin('$1/$2/', href.split('#')[0])); break")
    [ -n "$url" ] || { echo "no $TAG wheel for $2 $3 in $1" >&2; exit 1; }
    curl -fsSL -o "$WHEELS/$(basename "$url")" "$url"
}

# a wheel built from PyPI's sdist: build_wheel <name> <version> [env for cibuildwheel...]
build_wheel() {
    local name=$1 version=$2; shift 2
    ls "$WHEELS"/${name//-/_}-$version-*.whl > /dev/null 2>&1 && return
    echo "building $name $version ($TARGET)"
    local sdist
    sdist=$(curl -fsSL "https://pypi.org/pypi/$name/$version/json" | python3 -c \
        "import json,sys; print(next(u['url'] for u in json.load(sys.stdin)['urls'] if u['packagetype']=='sdist'))")
    [ -f "$SRC/$(basename "$sdist")" ] || curl -fsSL -o "$SRC/$(basename "$sdist")" "$sdist"
    # CIBW_ARCHS: the default (auto) is the machine's own, so an x86_64 Linux
    # runner selected no arm64 Android build; CIBW_BUILD picks the one we want
    env CIBW_BUILD="$CIBW" CIBW_ARCHS=all CIBW_TEST_SKIP='*' "$@" \
        uvx cibuildwheel@$CIBUILDWHEEL_VERSION --platform $PLATFORM --output-dir "$WHEELS" \
        "$SRC/$(basename "$sdist")" > "$WORK/$TARGET-$name.log" 2>&1 || {
        tail -30 "$WORK/$TARGET-$name.log"; exit 1; }
}

BEEWARE=https://pypi.anaconda.org/beeware/simple
# numpy without BLAS (its own lapack_lite), as numpy's Pyodide build; when
# cross-compiling it can't run its probe for long double's format
# (Android arm64: IEEE quad)
printf "[properties]\nlongdouble_format = 'IEEE_QUAD_LE'\n" > "$WORK/numpy-android.ini"
NUMPY_BUILD=(CIBW_BEFORE_BUILD= "CIBW_CONFIG_SETTINGS=setup-args=-Dblas=none setup-args=-Dlapack=none setup-args=-Dallow-noblas=true setup-args=--cross-file=$WORK/numpy-android.ini build-dir=build")
case $TARGET in
ios | ios-sim)
    fetch_wheel $BEEWARE numpy "$NUMPY_IOS_VERSION"
    fetch_wheel $BEEWARE cryptography "$CRYPTOGRAPHY_VERSION"
    fetch_wheel https://pypi.org/simple pillow "$PILLOW_VERSION"
    fetch_wheel https://pypi.org/simple cffi "$CFFI_VERSION"
    ;;
android)
    build_wheel numpy "$NUMPY_VERSION" "${NUMPY_BUILD[@]}"
    build_wheel cffi "$CFFI_VERSION" \
        CIBW_ENVIRONMENT="PKG_CONFIG_PATH=$ROOT/build/programs/android/prefix/lib/pkgconfig"
    # its CI script for the image libraries isn't in the sdist: the ones
    # build_programs.sh built (libjpeg-turbo, libpng, libwebp, FreeType)
    # (and the NDK's zlib, which it doesn't look for in the sysroot)
    PREFIX=$ROOT/build/programs/android/prefix
    NDK=${ANDROID_NDK_ROOT:-$ANDROID_HOME/ndk/28.2.13676358}
    SYSROOT=$(echo "$NDK"/toolchains/llvm/prebuilt/*/sysroot/usr)
    ZLIB=$WORK/android-zlib
    mkdir -p "$ZLIB/include" "$ZLIB/lib"
    ln -sf "$SYSROOT/include/zlib.h" "$SYSROOT/include/zconf.h" "$ZLIB/include/"
    ln -sf "$SYSROOT/lib/aarch64-linux-android/28/libz.so" "$ZLIB/lib/"
    # platform-guessing: on a Linux machine Pillow adds /usr/include and
    # /usr/lib, the host's glibc headers ("bits/wordsize.h" not found)
    build_wheel pillow "$PILLOW_VERSION" CIBW_BEFORE_ALL= \
        CIBW_CONFIG_SETTINGS="raqm=disable imagequant=disable xcb=disable avif=disable platform-guessing=disable" \
        CIBW_ENVIRONMENT="CFLAGS=-I$PREFIX/include LDFLAGS=-L$PREFIX/lib PKG_CONFIG_PATH=$PREFIX/lib/pkgconfig ZLIB_ROOT=$ZLIB"
    # Rust ignores LDFLAGS: 16 KB pages (Android 15+ devices) and libpython
    # (Android resolves extension modules' Python symbols only through it;
    # PyO3's abi3 build leaves it out) go in RUSTFLAGS
    build_wheel cryptography "$CRYPTOGRAPHY_VERSION" \
        CIBW_ENVIRONMENT="RUSTFLAGS='-C link-arg=-Wl,-z,max-page-size=16384 -C link-arg=-lpython$PYTHON_VERSION'"
    ;;
esac

# pure Python, the same everywhere: pyOpenSSL and pycparser (they need
# cryptography and cffi, so not in requirements.in) and jieba (no wheel on PyPI)
for pure in "pyopenssl==$PYOPENSSL_VERSION" "pycparser==$PYCPARSER_VERSION"; do
    ls "$WHEELS"/${pure%%==*}-${pure##*==}-*.whl > /dev/null 2>&1 ||
        uvx pip download -q --no-deps --only-binary :all: --platform any \
            --python-version "$PYTHON_VERSION" --implementation py --abi none -d "$WHEELS" "$pure"
done
ls "$WHEELS"/jieba-$JIEBA_VERSION-*.whl > /dev/null 2>&1 ||
    uvx pip wheel -q --no-deps -w "$WHEELS" "jieba==$JIEBA_VERSION"

rm -rf "$SITE" && mkdir -p "$SITE"
for w in "$WHEELS"/*.whl; do unzip -qo -DD "$w" -d "$SITE"; done
# metadata and the packages' tests aren't needed in the app
rm -rf "$SITE"/*.dist-info/RECORD "$SITE"/numpy/*/tests "$SITE"/numpy/tests
du -sh "$SITE"
