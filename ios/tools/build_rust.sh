#!/bin/bash
# Build Anki's rsbridge and the orjson / rpds-py extension modules as static
# libraries for iOS. pyo3 is told not to link libpython; the app links
# Python.framework itself.
# Usage: build_rust.sh [aarch64-apple-ios|aarch64-apple-ios-sim]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
TARGET=${1:-aarch64-apple-ios}
export IPHONEOS_DEPLOYMENT_TARGET=16.0

# Anki pins its toolchain (rust-toolchain.toml); orjson needs a newer rustc
# than that, so it uses nightly.
ANKI_TOOLCHAIN=$(sed -n 's/^channel *= *"\(.*\)"/\1/p' "$ROOT/deps/anki/rust-toolchain.toml")
for toolchain in "$ANKI_TOOLCHAIN" nightly stable; do
    rustup toolchain install --profile minimal "$toolchain" >/dev/null
    rustup target add --toolchain "$toolchain" "$TARGET" >/dev/null
done
export PROTOC=${PROTOC:-$(command -v protoc)}

# rsbridge refuses to load unless its build hash matches the Python package's
mkdir -p "$ROOT/deps/anki/out"
HASH=$(git -C "$ROOT/deps/anki" rev-parse --short=8 HEAD)
# rewriting it unchanged would still rebuild the whole core
[ "$(cat "$ROOT/deps/anki/out/buildhash" 2>/dev/null)" = "$HASH" ] \
    || echo "$HASH" > "$ROOT/deps/anki/out/buildhash"

cd "$ROOT/deps/anki"
# link-time optimization, as Anki's release-lto profile: the translations are
# generated as consts, which without it end up in the binary twice (~8 MB)
CARGO_PROFILE_RELEASE_LTO=fat CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 \
PYO3_CONFIG_FILE=$ROOT/../shared/tools/pyo3/abi3.cfg cargo rustc -p rsbridge --lib --release \
    --target "$TARGET" --features rustls --crate-type staticlib

export PYO3_CONFIG_FILE=$ROOT/../shared/tools/pyo3/cp314.cfg
cd "$ROOT/deps/sdist/orjson-$ORJSON_VERSION"
cargo +nightly rustc --lib --release --target "$TARGET" --crate-type staticlib
cd "$ROOT/deps/sdist/rpds_py-$RPDS_VERSION"
cargo +stable rustc --lib --release --target "$TARGET" --crate-type staticlib
