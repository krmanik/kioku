#!/bin/bash
# Write a pyo3 config for shared/versions.env's PYTHON_VERSION from one of the
# templates here (@PYTHON_VERSION@) and print its path. The path stays the
# same and the file is only rewritten when it changes, so cargo doesn't
# rebuild the extension modules for nothing.
# Usage: PYO3_CONFIG_FILE=$(config.sh <template.cfg>)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/../../versions.env"
mkdir -p "$HERE/../../../build/pyo3"
out=$(cd "$HERE/../../../build/pyo3" && pwd)/$(basename "$1")
new=$(sed "s/@PYTHON_VERSION@/$PYTHON_VERSION/g" "$1")
[ -f "$out" ] && [ "$(cat "$out")" = "$new" ] || printf '%s\n' "$new" > "$out"
echo "$out"
