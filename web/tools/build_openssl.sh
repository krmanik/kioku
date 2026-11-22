#!/bin/bash
# OpenSSL for Emscripten (static, with pthreads like everything else) into
# CPython's cross-build prefix, for the ssl and hashlib modules
# (build_python.sh configures CPython --with-openssl). Python's HTTPS
# (add-on downloads, add-ons' own requests) then runs inside wasm over
# Emscripten's sockets and the relay in tools/serve.py.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$ROOT/deps/emsdk/emsdk_env.sh" >/dev/null 2>&1
V=3.5.4
SRC=$ROOT/deps/openssl-$V
PREFIX=${1:?usage: build_openssl.sh <prefix>}  # build_python.sh passes its cross-build prefix
[ -d "$SRC" ] || curl -sL "https://github.com/openssl/openssl/releases/download/openssl-$V/openssl-$V.tar.gz" | tar xz -C "$ROOT/deps"
cd "$SRC"
./Configure linux-generic32 no-asm no-shared no-dso no-engine no-afalgeng no-tests \
    no-apps no-docs no-ui-console no-async -pthread \
    --prefix="$PREFIX" --libdir=lib --openssldir=/etc/ssl \
    CC=emcc CXX=em++ AR=emar RANLIB=emranlib
make -j8 build_libs
make install_dev
