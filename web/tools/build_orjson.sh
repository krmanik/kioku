#!/bin/bash
# Build orjson (Rust; Anki's JSON in and out of its core is faster with it,
# it falls back to json without) as a static library with rsbridge's flags,
# from the sdist Kioku's iOS build fetches, like build_rpds.sh. Linked in and
# registered as the built-in module `orjson.orjson` (src/main.cpp), like iOS;
# Pyodide builds it for Emscripten the same way. Built from a copy without
# the sdist's .cargo/config.toml: it points crates.io at the vendored crates,
# which -Zbuild-std's own crates aren't among.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$ROOT/deps/emsdk/emsdk_env.sh" >/dev/null 2>&1
SDIST=$(ls -d "$KIOKU_REPO"/ios/deps/sdist/orjson-*/ | grep -v '\.tar' | head -1)
SRC=$ROOT/build/orjson-src
rsync -a --delete --exclude .cargo --exclude include/cargo "$SDIST" "$SRC/"
export CFLAGS_wasm32_unknown_emscripten="-pthread"
export CARGO_TARGET_DIR=$ROOT/build/rust-target-orjson
export RUSTFLAGS="-C panic=abort -C target-feature=+atomics,+bulk-memory,+mutable-globals"
cd "$SRC"
PYO3_CONFIG_FILE=$("$KIOKU_REPO/shared/tools/pyo3/config.sh" "$ROOT/tools/pyo3/cpython-wasm32.cfg") cargo +nightly rustc -Zbuild-std=std,panic_abort \
    --lib --release --target wasm32-unknown-emscripten --crate-type staticlib
