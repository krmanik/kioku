#!/bin/bash
source "$(dirname "$0")/env.sh"
# node harness: CPython + Anki's Rust core without Qt (tools/core/; run with
# `cd build/core && node run.mjs -c ...`). --allow-multiple-definition: 3.13
# has the HACL hashes in libpython too (3.14 left them out)
cd "$ROOT"
source deps/emsdk/emsdk_env.sh >/dev/null 2>&1
B=deps/Python-$PYTHON_FULL_VERSION/cross-build/wasm32-emscripten
mkdir -p build/core
emcc -O2 -pthread -DKIOKU_PYTHON_VERSION="\"$PYTHON_VERSION\"" tools/core/core_main.c -I$B/build/python -I deps/Python-$PYTHON_FULL_VERSION/Include -o build/core/core.mjs \
  build/rust-target/wasm32-unknown-emscripten/release/librsbridge.a $B/build/python/libpython$PYTHON_VERSION.a $B/build/python/Modules/expat/libexpat.a $B/build/python/Modules/_hacl/*.o $B/prefix/lib/libmpdec.a $B/prefix/lib/libffi.a \
  $B/prefix/lib/libssl.a $B/prefix/lib/libcrypto.a -sALLOW_TABLE_GROWTH -Wl,--allow-multiple-definition \
  -sUSE_ZLIB -sUSE_BZIP2 -sALLOW_MEMORY_GROWTH -sINITIAL_MEMORY=64MB -sSTACK_SIZE=5MB -sPROXY_TO_PTHREAD -sEXIT_RUNTIME -sFORCE_FILESYSTEM \
  --preload-file build/stdlib@/python/lib/python$PYTHON_VERSION --preload-file build/site@/site --preload-file tools/core@/app "$@" 2>&1 \
  | grep -v "pthreads-mem-growth" | head -30
