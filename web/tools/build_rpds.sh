#!/bin/bash
# Build rpds-py (Rust; jsonschema needs it through referencing, and Anki
# validates add-on manifests with jsonschema) as a static library with
# rsbridge's flags, from the sdist Kioku's iOS build fetches. Linked in
# and registered as the built-in module `rpds` (src/main.cpp), like iOS.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$ROOT/deps/emsdk/emsdk_env.sh" >/dev/null 2>&1
SRC=$(ls -d "$KIOKU_REPO"/ios/deps/sdist/rpds_py-*/ | grep -v '\.tar' | head -1)
export CFLAGS_wasm32_unknown_emscripten="-pthread"
export CARGO_TARGET_DIR=$ROOT/build/rust-target-rpds
export RUSTFLAGS="-C panic=abort -C target-feature=+atomics,+bulk-memory,+mutable-globals"
cd "$SRC"
PYO3_CONFIG_FILE=$("$KIOKU_REPO/shared/tools/pyo3/config.sh" "$ROOT/tools/pyo3/cpython-wasm32.cfg") cargo +nightly rustc -Zbuild-std=std,panic_abort \
    --lib --release --target wasm32-unknown-emscripten --crate-type staticlib
