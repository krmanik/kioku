#!/bin/bash
# The sip ABI (13.12) that the PyQt6-sip module at PYQT6_SIP_VERSION (the one
# Anki pins) implements, read from its sip.h. sip-build otherwise generates
# code for the newest ABI it knows, and PyQt6.QtCore then fails to import:
# "the sip module implements ABI v13.0 to v13.12 but the PyQt6.QtCore module
# requires ABI v13.13".
# Usage: sip-build --abi-version "$(sip_abi.sh <pyqt6_sip sdist dir>)" ...
set -euo pipefail
h=$1/sip.h
major=$(sed -n 's/^#define SIP_ABI_MAJOR_VERSION *\([0-9]*\)/\1/p' "$h")
minor=$(sed -n 's/^#define SIP_ABI_MINOR_VERSION *\([0-9]*\)/\1/p' "$h")
[ -n "$major" ] && [ -n "$minor" ] || { echo "no SIP_ABI_*_VERSION in $h" >&2; exit 1; }
echo "$major.$minor"
