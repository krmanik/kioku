#!/bin/bash
# Build Anki's rsbridge as a static library for wasm32-unknown-emscripten,
# with pthreads (atomics) and panic=abort: Qt's prebuilt wasm libraries use
# Emscripten's JS setjmp/longjmp, which can't be linked with wasm exception
# handling. Six dependencies need small emscripten patches (patches/*.patch,
# applied to copies in deps/patched/ that cargo picks up via --config).
# Built for size (opt-level s): at Anki's opt-level 3 the whole backend
# dispatch was inlined into one 1.4 MB wasm function, and Safari's optimizing
# compiler took hundreds of MB compiling it once it got hot (at start, during
# an import): an iPhone ended the tab. At s it is 830 KB and the tab stays.
set -uo pipefail
source "$(dirname "$0")/env.sh"
D=$ROOT/deps
source "$D/emsdk/emsdk_env.sh" >/dev/null 2>&1
REG=$(ls -d ~/.cargo/registry/src/index.crates.io-*/ | head -1)
for p in "$ROOT"/patches/{mio-1.0.4,tokio-1.47.1,socket2-0.6.0,reqwest-0.12.23,ring-0.17.14}.patch; do
    crate=$(basename "$p" .patch)
    if [ ! -d "$D/patched/$crate" ]; then
        mkdir -p "$D/patched" && cp -R "$REG/$crate" "$D/patched/" && patch -s -p0 -d "$D/patched/$crate" < "$p"
    fi
done
cd "$KIOKU_REPO/ios/deps/anki"
# the patches change the lock file; keep Anki's own untouched
mkdir -p "$ROOT/build"
cp Cargo.lock "$ROOT/build/Cargo.lock.anki"
trap 'cp Cargo.lock "$ROOT/build/anki-Cargo.lock"; cp "$ROOT/build/Cargo.lock.anki" Cargo.lock' EXIT
[ -f "$ROOT/build/anki-Cargo.lock" ] && cp "$ROOT/build/anki-Cargo.lock" Cargo.lock
export PROTOC=$(command -v protoc)
export CFLAGS_wasm32_unknown_emscripten="-pthread" CXXFLAGS_wasm32_unknown_emscripten="-pthread"
export CARGO_TARGET_DIR=$ROOT/build/rust-target
export RUSTFLAGS="-C panic=abort -C target-feature=+atomics,+bulk-memory,+mutable-globals --cfg tokio_unstable --cfg mio_unsupported_force_poll_poll --cfg mio_unsupported_force_waker_pipe"
PYO3_CONFIG_FILE=$("$KIOKU_REPO/shared/tools/pyo3/config.sh" "$KIOKU_REPO/shared/tools/pyo3/abi3.cfg") cargo +nightly rustc -Zbuild-std=std,panic_abort \
    --config "patch.crates-io.mio.path=\"$D/patched/mio-1.0.4\"" \
    --config "patch.crates-io.tokio.path=\"$D/patched/tokio-1.47.1\"" \
    --config "patch.crates-io.socket2.path=\"$D/patched/socket2-0.6.0\"" \
    --config "patch.crates-io.reqwest.path=\"$D/patched/reqwest-0.12.23\"" \
    --config "patch.crates-io.ring.path=\"$D/patched/ring-0.17.14\"" \
    --config 'profile.release.opt-level="s"' \
    "$@" -p rsbridge --lib --release --target wasm32-unknown-emscripten --features rustls --crate-type staticlib
