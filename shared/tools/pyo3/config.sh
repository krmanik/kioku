#!/bin/bash
# Write a pyo3 config for shared/versions.env's PYTHON_VERSION from one of the
# templates here (@PYTHON_VERSION@) and print its path.
# Usage: PYO3_CONFIG_FILE=$(config.sh <template.cfg>)
set -euo pipefail
source "$(dirname "$0")/../../versions.env"
out=${TMPDIR:-/tmp}/kioku-pyo3-$PYTHON_VERSION-$(basename "$1")
sed "s/@PYTHON_VERSION@/$PYTHON_VERSION/g" "$1" > "$out"
echo "$out"
