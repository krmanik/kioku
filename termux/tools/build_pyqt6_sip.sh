#!/bin/sh
# Cross-compile PyQt6.sip for Termux's Python with the Android NDK.
#
# Termux's pyqt6 package pip-installs PyQt6-sip from source in its postinst,
# which needs a compiler on the phone. Build it here instead and ship it as an
# overlay for tools/build_rootfs.py (--extra).
#
#   tools/build_pyqt6_sip.sh build/rootfs-repo/usr 3.14 build/pyqt6-sip-overlay
#
# The sip module must implement the sip ABI the prefix's PyQt6 was built for
# (sip-abi-version in PyQt6/bindings/QtCore/QtCore.toml), or every PyQt6 import
# fails with "the sip module implements ABI v13.0 to v13.12 but the
# PyQt6.QtCore module requires ABI v13.13". Termux upgrades pyqt6 on its own
# schedule, so take the newest PyQt6-sip of that ABI's major version (newer
# minors implement all older ones) and check the source's ABI before building.
# PYQT6_SIP_VERSION=x.y.z pins a version instead; it must still cover the ABI.
set -eu

PREFIX_TREE="${1:?prefix tree containing include/pythonX.Y and lib/libpythonX.Y.so}"
PYVER="${2:?python version, e.g. 3.14}"
OUT="${3:?output overlay dir}"
API="${ANDROID_API:-24}"
NDK="${ANDROID_NDK:-$HOME/Library/Android/sdk/ndk/30.0.14904198}"

# The newest ABI any of the prefix's bindings (PyQt6, PyQt6-WebEngine) needs.
BINDINGS="$PREFIX_TREE/lib/python$PYVER/site-packages/PyQt6/bindings"
ABI="$(sed -n 's/^sip-abi-version = "\([0-9]*\.[0-9]*\)"/\1/p' "$BINDINGS"/*/*.toml 2>/dev/null \
	| sort -t. -k1,1n -k2,2n | tail -1)"
[ -n "$ABI" ] || { echo "no sip-abi-version in $BINDINGS/*/*.toml" >&2; exit 1; }
ABI_MAJOR="${ABI%.*}"
ABI_MINOR="${ABI#*.}"

if [ -z "${PYQT6_SIP_VERSION:-}" ]; then
	PYQT6_SIP_VERSION="$(curl -fsSL https://pypi.org/pypi/PyQt6-sip/json | python3 -I -c '
import json, re, sys
major = int(sys.argv[1])
releases = json.load(sys.stdin)["releases"]
best = None
for v, files in releases.items():
    m = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", v)
    has_sdist = any(f["packagetype"] == "sdist" and not f["yanked"] for f in files)
    if m and int(m[1]) == major and has_sdist:
        key = tuple(int(x or 0) for x in m.groups())
        best = max(best or key, key)
if best is None:
    sys.exit(f"no PyQt6-sip release for sip ABI {major} on PyPI")
print(".".join(map(str, best)))
' "$ABI_MAJOR")"
fi
echo "PyQt6 needs sip ABI $ABI: building PyQt6-sip $PYQT6_SIP_VERSION"

CC="$(ls -d "$NDK"/toolchains/llvm/prebuilt/*/bin | head -1)/clang"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 -m pip download --quiet --no-deps --no-binary :all: "PyQt6-sip==$PYQT6_SIP_VERSION" -d "$WORK"
tar xzf "$WORK"/pyqt6_sip-"$PYQT6_SIP_VERSION".tar.gz -C "$WORK"
SRC="$WORK/pyqt6_sip-$PYQT6_SIP_VERSION"

# The ABI this sip module implements: the same major, minors up to its own.
HAS_MAJOR="$(sed -n 's/^#define SIP_ABI_MAJOR_VERSION[[:space:]]*\([0-9]*\).*/\1/p' "$SRC/sip.h")"
HAS_MINOR="$(sed -n 's/^#define SIP_ABI_MINOR_VERSION[[:space:]]*\([0-9]*\).*/\1/p' "$SRC/sip.h")"
if [ "$HAS_MAJOR" != "$ABI_MAJOR" ] || [ "${HAS_MINOR:-0}" -lt "$ABI_MINOR" ]; then
	echo "PyQt6-sip $PYQT6_SIP_VERSION implements sip ABI $HAS_MAJOR.$HAS_MINOR, but PyQt6 needs $ABI" >&2
	exit 1
fi

rm -rf "$OUT"
SITE="$OUT/lib/python$PYVER/site-packages"
mkdir -p "$SITE/PyQt6"
TAG="cpython-$(echo "$PYVER" | tr -d .)"
# Termux Python only loads extensions with its full platform suffix.
SUFFIX="$TAG-aarch64-linux-android"
# Android's linker, unlike glibc's, needs extensions to link libpython.
"$CC" --target="aarch64-linux-android$API" -shared -fPIC -O2 \
	-I"$PREFIX_TREE/include/python$PYVER" -I"$SRC" \
	"$SRC"/*.c -L"$PREFIX_TREE/lib" -lpython"$PYVER" \
	-o "$SITE/PyQt6/sip.$SUFFIX.so"
"$(dirname "$CC")/llvm-strip" "$SITE/PyQt6/sip.$SUFFIX.so"

DIST="$SITE/pyqt6_sip-$PYQT6_SIP_VERSION.dist-info"
mkdir -p "$DIST"
printf 'Metadata-Version: 2.1\nName: PyQt6-sip\nVersion: %s\n' "$PYQT6_SIP_VERSION" > "$DIST/METADATA"
printf 'Wheel-Version: 1.0\nGenerator: kioku\nRoot-Is-Purelib: false\nTag: %s-%s-android_%s_arm64_v8a\n' \
	"$(echo "$TAG" | sed 's/cpython-/cp/')" "$(echo "$TAG" | sed 's/cpython-/cp/')" "$API" > "$DIST/WHEEL"
printf 'pip\n' > "$DIST/INSTALLER"
echo "built $SITE/PyQt6/sip.$SUFFIX.so (sip ABI $HAS_MAJOR.$HAS_MINOR)"
