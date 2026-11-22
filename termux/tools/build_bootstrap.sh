#!/bin/sh
# Build app/src/main/assets/bootstrap-aarch64.zip from Termux packages.
#
#   tools/build_bootstrap.sh [APP_ID [ROOTFS_DIR]]
#
# APP_ID and ROOTFS_DIR default to ankideskApplicationId and ankideskRootfsDir
# from gradle.properties. Packages come from the official Termux repositories,
# plus the .debs of the krmanik/termux-packages release anki-<ANKI_TAG> (anki and
# the Python packages built for the Python Anki pins: python, python-pip, pyqt6,
# python-pyqt6-webengine, python-rpds-py, python-markupsafe, python-orjson;
# tools/fetch_anki_debs.py) and any .debs in local-debs/, which take precedence
# in that order. For packages rebuilt for
# APP_ID by tools/build-termux-packages.sh, put them in local-debs/ and run
# with SOURCE_PACKAGE=APP_ID and ROOTFS_DIR=files.
set -eu

cd "$(dirname "$0")/.."
APP_ID="${1:-$(sed -n 's/^ankideskApplicationId=//p' gradle.properties)}"
ROOTFS_DIR="${2:-$(sed -n 's/^ankideskRootfsDir=//p' gradle.properties)}"
# The Python Anki pins (shared/versions.env), which the anki-<ANKI_TAG> release
# is built for; Termux's own is newer
PYVER="${PYVER:-$(sed -n 's/^PYTHON_VERSION=//p' ../shared/versions.env)}"
export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/cert.pem}"

# xorg-server-xvfb, x11vnc: the remote desktop (ankidesk_remote.py), about 8 MB
ROOTS="anki,jwm,st,dash,termux-exec,xkeyboard-config,ca-certificates,resolv-conf,python-rpds-py,xorg-server-xvfb,x11vnc"
# Pulled in by dependencies but never used at runtime; pruned anyway.
SKIP="perl,libllvm,mesa-vulkan-icd-swrast,gstreamer,gst-plugins-base,gst-plugins-bad,gst-libav,make,make-guile"

echo "== packages for $APP_ID (/data/data/$APP_ID/$ROOTFS_DIR/usr)"
python3 -I tools/fetch_anki_debs.py --out build/anki-debs
python3 -I tools/fetch_debs.py --roots "$ROOTS" --local build/anki-debs --local local-debs --skip "$SKIP" \
	--out build/debs --list build/debs-closure.tsv
# Package name the .debs were built for (com.termux for the official repos).
python3 -I tools/debs_to_prefix.py --package "${SOURCE_PACKAGE:-com.termux}" --debs build/debs --out build/rootfs-repo
# Python and PyQt6 as Anki pins them, not a Termux repository build (#23)
python3 -I tools/check_runtime_pins.py build/rootfs-repo/usr

echo "== PyQt6.sip, PyQt6.QtPdf and pure-Python dependencies"
# the PyQt6-sip Anki pins; fails if PyQt6 was built for a newer sip ABI
PYQT6_SIP_VERSION="$(sed -n 's/^PYQT6_SIP_VERSION=//p' ../shared/versions.env)" \
	tools/build_pyqt6_sip.sh build/rootfs-repo/usr "$PYVER" build/pyqt6-sip-overlay
tools/build_pyqt6_pdf.sh build/rootfs-repo/usr "$PYVER" build/pyqt6-pdf-overlay
tools/fetch_python_deps.sh "$PYVER" build/python-deps

tools/fetch_novnc.sh build/novnc-overlay

# Shared with the native apps (launch_anki.py): Preferences > Advanced, add-on docks.
# Every kioku module launch_anki.py reaches through imports, not a hand-kept list.
rm -rf build/kioku-overlay
mkdir -p build/kioku-overlay/share/ankidx/kioku
MODULES=$(python3 -I tools/kioku_modules.py)
for m in $MODULES; do
	cp ../shared/python/kioku/$m.py build/kioku-overlay/share/ankidx/kioku/
done

# The app installer treats these as already installed.
mkdir -p build/base-overlay/var/lib/ankidesk
cp build/debs-closure.tsv build/base-overlay/var/lib/ankidesk/base-packages.tsv

echo "== bootstrap"
python3 -I tools/build_rootfs.py --src build/rootfs-repo/usr --owners build/rootfs-repo/file-owners.tsv \
	--extra rootfs-overlay --extra build/python-deps --extra build/pyqt6-sip-overlay --extra build/pyqt6-pdf-overlay --extra build/base-overlay --extra build/novnc-overlay --extra build/kioku-overlay \
	--package "$APP_ID" --rootfs-dir "$ROOTFS_DIR" --stage build/rootfs-stage --out app/src/main/assets/bootstrap-aarch64.zip
