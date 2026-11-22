#!/bin/bash
# Build Anki's Python (PYTHON_FULL_VERSION, shared/versions.env) for
# Emscripten 4.0.7 (Qt 6.11's version) with pthreads, statically, without
# PY_CALL_TRAMPOLINE: Asyncify (QDialog.exec()) can't unwind through the
# trampoline's JS frame, and the stdlib, sip and pyo3 work with plain indirect
# calls. The steps are those of 3.14's Tools/wasm/emscripten (3.13 has no such
# driver): a build Python, libffi and mpdecimal into the cross-build prefix,
# OpenSSL (build_openssl.sh), then CPython itself. The stdlib copy for the
# virtual file system goes to build/stdlib.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$ROOT/deps/emsdk/emsdk_env.sh" >/dev/null 2>&1
PY=$ROOT/deps/Python-$PYTHON_FULL_VERSION
CROSS=$PY/cross-build
PREFIX=$CROSS/wasm32-emscripten/prefix
HOST=$CROSS/wasm32-emscripten/build/python
JOBS=$(sysctl -n hw.ncpu 2>/dev/null || nproc)
if [ ! -d "$PY" ]; then
    curl -fsSL "https://www.python.org/ftp/python/$PYTHON_FULL_VERSION/Python-$PYTHON_FULL_VERSION.tar.xz" \
        | tar xJ -C "$ROOT/deps"
fi

fetch() {  # fetch <url> <sha256> <dir>: unpack into $CROSS/wasm32-emscripten/build
    [ -d "$CROSS/wasm32-emscripten/build/$3" ] && return
    mkdir -p "$CROSS/wasm32-emscripten/build"
    curl -fsSL -o "$CROSS/download.tar.gz" "$1"
    echo "$2  $CROSS/download.tar.gz" | shasum -a 256 -c --quiet
    tar xzf "$CROSS/download.tar.gz" -C "$CROSS/wasm32-emscripten/build"
    rm "$CROSS/download.tar.gz"
}

# the build machine's Python (cross-compiling runs it); python.exe on macOS,
# where a file named python would clash with the Python/ directory
BUILD_PYTHON=$CROSS/build/python
[ "$(uname)" = Darwin ] && BUILD_PYTHON=$CROSS/build/python.exe
if [ ! -f "$BUILD_PYTHON" ]; then
    mkdir -p "$CROSS/build"
    (cd "$CROSS/build" && ../../configure -q && make -j "$JOBS" all > make.log)
fi

# libffi (ctypes) and mpdecimal (decimal), as Tools/wasm/emscripten builds them
if [ ! -f "$PREFIX/lib/libffi.a" ]; then
    fetch https://github.com/libffi/libffi/releases/download/v3.4.6/libffi-3.4.6.tar.gz \
        b0dea9df23c863a7a50e825440f3ebffabd65df1497108e5d437747843895a4e libffi-3.4.6
    (cd "$CROSS/wasm32-emscripten/build/libffi-3.4.6" \
        && CFLAGS="-O2 -fPIC -DWASM_BIGINT" CXXFLAGS="-O2 -fPIC -DWASM_BIGINT" CPATH="$PREFIX/include" \
           PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" EM_PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" \
           emconfigure ./configure --host=wasm32-unknown-linux --prefix="$PREFIX" --enable-static \
               --disable-shared --disable-dependency-tracking --disable-builddir \
               --disable-multi-os-directory --disable-raw-api --disable-docs > /dev/null \
        && make install > /dev/null \
        && cp fficonfig.h include/ffi_common.h "$PREFIX/include/")
fi
if [ ! -f "$PREFIX/lib/libmpdec.a" ]; then
    fetch https://www.bytereef.org/software/mpdecimal/releases/mpdecimal-4.0.1.tar.gz \
        96d33abb4bb0070c7be0fed4246cd38416188325f820468214471938545b1ac8 mpdecimal-4.0.1
    (cd "$CROSS/wasm32-emscripten/build/mpdecimal-4.0.1" \
        && emconfigure ./configure CFLAGS=-fPIC --prefix="$PREFIX" --disable-shared > /dev/null \
        && make install > /dev/null)
fi
[ -f "$PREFIX/lib/libssl.a" ] || "$ROOT/tools/build_openssl.sh" "$PREFIX"  # ssl, hashlib

# CPython: the config.site moved to Tools/wasm/emscripten/ in 3.14
# 3.13's says Emscripten has no sys/ioctl.h, which leaves out the fcntl
# module: with it, opening any file failed (ioctl(FIOCLEX) gives EINVAL,
# which only 3.14's own syscall overrides turn into ENOTTY)
CONFIG_SITE=$PY/Tools/wasm/emscripten/config.site-wasm32-emscripten
[ -f "$CONFIG_SITE" ] || CONFIG_SITE=$PY/Tools/wasm/config.site-wasm32-emscripten
mkdir -p "$HOST"
cd "$HOST"
if [ ! -f Makefile ]; then
    CONFIG_SITE=$CONFIG_SITE EM_PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" \
    emconfigure ../../../../configure -q \
        CFLAGS="-sUSE_BZIP2" PKG_CONFIG=pkg-config \
        --host=wasm32-unknown-emscripten --build="$("$PY/config.guess")" \
        --with-build-python="$BUILD_PYTHON" --with-emscripten-target=node \
        --without-pymalloc --disable-shared --disable-ipv6 --enable-big-digits=30 \
        --enable-wasm-pthreads --disable-wasm-dynamic-linking \
        --with-openssl="$PREFIX" --prefix="$PREFIX"
fi
# the static library and the modules in it are what the app links; the
# python.js/.mjs link at the end needs a node setup the app doesn't use
emmake make -j "$JOBS" all > make.log 2>&1 || true
for f in "libpython$PYTHON_VERSION.a" Modules/expat/libexpat.a; do
    [ -f "$f" ] || { tail -30 make.log; echo "no $HOST/$f" >&2; exit 1; }
done
rsync -a --delete --exclude __pycache__ --exclude test --exclude tests --exclude idlelib \
    --exclude tkinter --exclude turtledemo --exclude ensurepip --exclude pydoc_data \
    "$PY/Lib/" "$ROOT/build/stdlib/"
cp build/lib.emscripten-*/_sysconfigdata__emscripten_wasm32-emscripten.py "$ROOT/build/stdlib/"
