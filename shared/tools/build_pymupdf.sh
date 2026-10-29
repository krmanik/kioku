#!/bin/bash
# Build PyMuPDF for the native apps: MuPDF's C library (with its third-party
# libraries), the C++ and Python bindings MuPDF generates for itself
# (scripts/mupdfwrap.py, run on the build machine with libclang and SWIG),
# and PyMuPDF's own extension (src/extra.i).
#   ios, ios-sim: one static library with PyInit__mupdf and PyInit__extra, linked
#            into the app (pymupdf._mupdf and pymupdf._extra in main.mm)
#   android: _mupdf.so and _extra.so over libmupdfcpp.so (MuPDF and the C++
#            bindings; both modules need the same MuPDF), in site/pymupdf/
# Output: build/pymupdf/<target>/ with lib/ and site/ (pymupdf/, fitz/).
# Usage: build_pymupdf.sh ios|ios-sim|android
# Env: ANDROID_NDK_ROOT (android), JOBS (default: all cores)
set -euo pipefail
SHARED=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$SHARED/.." && pwd)
source "$SHARED/versions.env"
TARGET=${1:?ios, ios-sim or android}
WORK=$ROOT/build/pymupdf
SRC=$WORK/src
MUPDF=$SRC/mupdf-$MUPDF_VERSION-source
PYMUPDF=$SRC/pymupdf-$PYMUPDF_VERSION
OUT=$WORK/$TARGET
JOBS=${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || nproc)}
mkdir -p "$SRC"

# Sources --------------------------------------------------------------------
if [ ! -d "$MUPDF" ]; then
    curl -fsSL "https://mupdf.com/downloads/archive/mupdf-$MUPDF_VERSION-source.tar.gz" \
        | tar xz -C "$SRC"
fi
if [ ! -d "$PYMUPDF" ]; then
    url=$(curl -fsSL "https://pypi.org/pypi/pymupdf/$PYMUPDF_VERSION/json" | python3 -c \
        "import json,sys; print(next(u['url'] for u in json.load(sys.stdin)['urls'] if u['packagetype']=='sdist'))")
    curl -fsSL "$url" | tar xz -C "$SRC" --exclude '*/tests/*'
fi

# Bindings source, generated on the build machine (same for every target) ----
VENV=$WORK/venv
if [ ! -x "$VENV/bin/python" ]; then
    uv venv -q -p "$PYTHON_VERSION" "$VENV"
    uv pip install -q -p "$VENV/bin/python" pip libclang pipcl
fi
if [ ! -s "$MUPDF/platform/python/mupdfcpp_swig.i.cpp" ]; then
    # mupdfwrap installs what it misses with whichever pip is first on PATH
    (cd "$MUPDF" && VIRTUAL_ENV=$VENV PATH=$VENV/bin:$PATH \
        python scripts/mupdfwrap.py -d build/shared-release -b 02)
fi
if [ ! -s "$PYMUPDF/src/build/extra.cpp" ]; then
    mkdir -p "$PYMUPDF/src/build"
    swig -Wall -c++ -python -module extra -outdir "$PYMUPDF/src/build" \
        -o "$PYMUPDF/src/build/extra.cpp" \
        -I"$MUPDF/include" -I"$MUPDF/platform/c++/include" "$PYMUPDF/src/extra.i"
fi

# Toolchain --------------------------------------------------------------------
# TOFU_CJK_EXT: like PyPI's PyMuPDF, without the extended CJK font
FLAGS="-fPIC -DTOFU_CJK_EXT"
case $TARGET in
ios | ios-sim)
    SDKNAME=iphoneos
    PYSLICE=ios-arm64
    VERSION_MIN=-miphoneos-version-min=17.0
    if [ "$TARGET" = ios-sim ]; then
        SDKNAME=iphonesimulator
        PYSLICE=ios-arm64_x86_64-simulator
        VERSION_MIN=-mios-simulator-version-min=17.0
    fi
    SDK=$(xcrun --sdk $SDKNAME --show-sdk-path)
    CC="$(xcrun --sdk $SDKNAME -f clang)"
    CXX="$(xcrun --sdk $SDKNAME -f clang++)"
    AR="$(xcrun --sdk $SDKNAME -f ar)"
    RANLIB="$(xcrun --sdk $SDKNAME -f ranlib)"
    FLAGS="$FLAGS -arch arm64 -isysroot $SDK $VERSION_MIN"
    PYINC=$ROOT/ios/deps/python-ios/Python.xcframework/$PYSLICE/include/python$PYTHON_VERSION
    ;;
android)
    NDK=${ANDROID_NDK_ROOT:-${ANDROID_NDK:?set ANDROID_NDK_ROOT}}
    LLVM=$NDK/toolchains/llvm/prebuilt/$( [ "$(uname)" = Darwin ] && echo darwin-x86_64 || echo linux-x86_64 )/bin
    CC=$LLVM/aarch64-linux-android28-clang
    CXX=$LLVM/aarch64-linux-android28-clang++
    AR=$LLVM/llvm-ar
    RANLIB=$LLVM/llvm-ranlib
    PYPREFIX=$ROOT/android/deps/python-android/prefix
    PYINC=$PYPREFIX/include/python$PYTHON_VERSION
    ;;
*)
    echo "unknown target $TARGET" >&2; exit 1 ;;
esac

# MuPDF and its third-party libraries -------------------------------------------
# OS: neither Darwin nor Linux, so no host libraries are looked up and fonts
# are compiled in as C arrays
make -C "$MUPDF" -j"$JOBS" OS=kioku-$TARGET build=release build_prefix=kioku-$TARGET- \
    CC="$CC" CXX="$CXX" AR="$AR" RANLIB="$RANLIB" XCFLAGS="$FLAGS" \
    HAVE_LIBCRYPTO=no HAVE_X11=no HAVE_GLUT=no libs
MUBUILD=$MUPDF/build/kioku-$TARGET-release

# C++ bindings, the _mupdf module and PyMuPDF's _extra -------------------------
OBJ=$OUT/obj
mkdir -p "$OBJ"
# SWIG dropped PyString_FromString with Python 2 (4.4); both .i files still use it
CXXFLAGS="$FLAGS -O2 -DNDEBUG -DPyString_FromString=PyUnicode_FromString \
    -I$MUPDF/include -I$MUPDF/platform/c++/include -I$PYINC"
compile() {  # compile <source> <object> [extra flags]
    [ "$2" -nt "$1" ] && return
    echo "compiling $(basename "$1")"
    "$CXX" -c $CXXFLAGS ${3:-} -o "$2.tmp" "$1" && mv "$2.tmp" "$2"
}
CPP_OBJS=()
PIDS=()
for f in "$MUPDF"/platform/c++/implementation/*.cpp; do
    o=$OBJ/$(basename "$f" .cpp).o
    compile "$f" "$o" & PIDS+=($!)
    CPP_OBJS+=("$o")
done
compile "$MUPDF/platform/python/mupdfcpp_swig.i.cpp" "$OBJ/_mupdf.o" -Wno-deprecated-declarations &
PIDS+=($!)
# PyMuPDF builds extra with -std=c++14 on macOS (MuPDF's exception classes)
compile "$PYMUPDF/src/build/extra.cpp" "$OBJ/_extra.o" "-std=c++14 -Wno-non-pod-varargs" &
PIDS+=($!)
for pid in "${PIDS[@]}"; do wait "$pid"; done

LIB=$OUT/lib
rm -rf "$LIB" && mkdir -p "$LIB"
case $TARGET in
ios | ios-sim)
    # Qt links its own harfbuzz, libjpeg, ...: prelink into one object that
    # exports only the two module init functions, everything else local
    printf '%s\n' _PyInit__mupdf _PyInit__extra > "$OBJ/exports.txt"
    xcrun ld -r -arch arm64 -o "$OBJ/pymupdf.o" -exported_symbols_list "$OBJ/exports.txt" \
        "${CPP_OBJS[@]}" "$OBJ/_mupdf.o" "$OBJ/_extra.o" \
        "$MUBUILD/libmupdf.a" "$MUBUILD/libmupdf-third.a"
    xcrun libtool -static -o "$LIB/libpymupdf.a" "$OBJ/pymupdf.o"
    ;;
android)
    SUFFIX=.cpython-${PYTHON_VERSION/./}-aarch64-linux-android.so
    # third-party symbols stay inside, apart from the copies Qt has
    "$CXX" -shared -o "$LIB/libmupdfcpp.so" -Wl,-soname,libmupdfcpp.so \
        -Wl,--gc-sections -Wl,--exclude-libs,libmupdf-third.a \
        -Wl,--whole-archive "$MUBUILD/libmupdf.a" -Wl,--no-whole-archive \
        "$MUBUILD/libmupdf-third.a" "${CPP_OBJS[@]}" -lm -llog
    for m in _mupdf _extra; do
        "$CXX" -shared -o "$LIB/$m$SUFFIX" "$OBJ/$m.o" -Wl,-rpath,'$ORIGIN' \
            -L"$LIB" -lmupdfcpp -L"$PYPREFIX/lib" -lpython$PYTHON_VERSION
    done
    "$LLVM/llvm-strip" --strip-unneeded "$LIB"/*.so
    ;;
esac

# Python files -----------------------------------------------------------------
SITE=$OUT/site
rm -rf "$SITE" && mkdir -p "$SITE/pymupdf" "$SITE/fitz"
for f in __init__ __main__ pymupdf table _table_refine _table_spans _table_union \
        _table_headers utils _wxcolors _apply_pages show_features; do
    [ -f "$PYMUPDF/src/$f.py" ] && cp "$PYMUPDF/src/$f.py" "$SITE/pymupdf/"
done
cp "$PYMUPDF/src/build/extra.py" "$MUPDF/build/shared-release/mupdf.py" "$SITE/pymupdf/"
cp "$PYMUPDF/src/fitz___init__.py" "$SITE/fitz/__init__.py"
cp "$PYMUPDF/src/fitz_table.py" "$SITE/fitz/table.py"
cp "$PYMUPDF/src/fitz_utils.py" "$SITE/fitz/utils.py"
SWIG_VERSION=$(swig -version | sed -n 's/^SWIG Version //p')
cat > "$SITE/pymupdf/_build.py" <<EOF
pymupdf_git_branch = None
pymupdf_git_diff = None
pymupdf_git_sha = None
mupdf_location = ''
pymupdf_version = '$PYMUPDF_VERSION'
pymupdf_version_tuple = (${PYMUPDF_VERSION//./, })
swig_version = '$SWIG_VERSION'
swig_version_tuple = (${SWIG_VERSION//./, })
fake_no_gil = False
EOF
if [ "$TARGET" = android ]; then cp "$LIB"/*.so "$SITE/pymupdf/"; fi
ls -la "$LIB"
