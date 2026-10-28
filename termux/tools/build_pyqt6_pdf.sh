#!/bin/sh
# Cross-compile PyQt6.QtPdf and PyQt6.QtPdfWidgets for Termux with the Android NDK.
#
# Termux's pyqt6 package is built without them (it doesn't depend on
# qt6-qtwebengine, which has libQt6Pdf), so add-ons that import PyQt6.QtPdf
# fail to load. Generate the bindings with sip against the PyQt6 bindings and
# Qt headers of the prefix tree, compile them here and ship them as an overlay
# for tools/build_rootfs.py (--extra).
#
#   tools/build_pyqt6_pdf.sh build/rootfs-repo/usr 3.14 build/pyqt6-pdf-overlay
set -eu

PREFIX_TREE="$(cd "${1:?prefix tree with include/qt6 and the PyQt6 bindings}" && pwd)"
PYVER="${2:?python version, e.g. 3.14}"
OUT="${3:?output overlay dir}"
API="${ANDROID_API:-24}"
NDK="${ANDROID_NDK:-$HOME/Library/Android/sdk/ndk/30.0.14904198}"

SITE_TREE="$PREFIX_TREE/lib/python$PYVER/site-packages"
BINDINGS="$SITE_TREE/PyQt6/bindings"
# Build the version of the prefix's PyQt6, against the sip ABI it was built with.
PYQT_VERSION="$(sed -n 's/^Version: //p' "$SITE_TREE"/[Pp]y[Qq]t6-*.dist-info/METADATA | head -1)"
SIP_ABI="$(sed -n 's/^sip-abi-version = "\(.*\)"/\1/p' "$BINDINGS/QtCore/QtCore.toml")"
# QtPdf comes with qt6-qtwebengine, which may be older than qt6-qtbase.
QT_VERSION="$(sed -n 's/^#define QTPDF_VERSION_STR "\(.*\)"/\1/p' "$PREFIX_TREE/include/qt6/QtPdf/qtpdfversion.h")"

BIN="$(ls -d "$NDK"/toolchains/llvm/prebuilt/*/bin | head -1)"
CXX="$BIN/clang++ --target=aarch64-linux-android$API"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet --disable-pip-version-check "sip>=6.16,<7" "PyQt-builder>=1.19,<2"
curl -fsSL "https://files.pythonhosted.org/packages/source/p/pyqt6/pyqt6-$PYQT_VERSION.tar.gz" \
	| tar xz -C "$WORK"
SDIST="$WORK/pyqt6-$PYQT_VERSION"

# sip-build only needs the Qt configuration from qmake (no test programs are
# built) and a Makefile to exist; the sources are compiled below.
cat > "$WORK/qmake" <<EOF
#!/bin/sh
[ "\$1" = -query ] || { touch Makefile; exit 0; }
cat <<END
QT_VERSION:$QT_VERSION
QT_INSTALL_PREFIX:$PREFIX_TREE
QT_INSTALL_HEADERS:$PREFIX_TREE/include/qt6
QT_INSTALL_LIBS:$PREFIX_TREE/lib
QT_INSTALL_BINS:$PREFIX_TREE/bin
QT_INSTALL_DATA:$PREFIX_TREE/lib/qt6
QMAKE_SPEC:linux-clang
QMAKE_XSPEC:linux-clang
END
EOF
chmod +x "$WORK/qmake"

PROJ="$WORK/project"
mkdir -p "$PROJ/sip"
cp -R "$SDIST/sip/QtPdf" "$SDIST/sip/QtPdfWidgets" "$PROJ/sip/"
cat > "$PROJ/pyproject.toml" <<EOF
[build-system]
requires = ["sip", "PyQt-builder"]
build-backend = "sipbuild.api"

[project]
name = "PyQt6-Pdf"
version = "$PYQT_VERSION"

[tool.sip]
project-factory = "pyqtbuild:PyQtProject"

[tool.sip.project]
abi-version = "$SIP_ABI"
sip-include-dirs = ["$BINDINGS"]
tag-prefix = "Qt"

[tool.sip.bindings.QtPdf]
qmake-QT = ["pdf"]

[tool.sip.bindings.QtPdfWidgets]
qmake-QT = ["pdfwidgets"]
EOF

(cd "$PROJ" && "$WORK/venv/bin/sip-build" --no-make --qmake "$WORK/qmake" --build-dir "$WORK/gen" >/dev/null)

SITE="$OUT/lib/python$PYVER/site-packages"
mkdir -p "$SITE/PyQt6"
QTINC="$PREFIX_TREE/include/qt6"
for mod in QtPdf QtPdfWidgets; do
	GEN="$WORK/gen/$mod"
	# the flags of the .pro file sip-build wrote
	for src in "$GEN"/*.cpp; do
		$CXX -std=c++17 -fPIC -O2 -fno-exceptions -DSIP_PROTECTED_IS_PUBLIC -Dprotected=public \
			-DPy_LIMITED_API=0x030a0000 -DQT_NO_DEBUG \
			-I"$GEN" -I"$WORK/gen" -I"$PREFIX_TREE/include/python$PYVER" -I"$QTINC" \
			-I"$QTINC/QtCore" -I"$QTINC/QtGui" -I"$QTINC/QtWidgets" -I"$QTINC/QtPdf" -I"$QTINC/QtPdfWidgets" \
			-c "$src" -o "${src%.cpp}.o"
	done
	# Android's linker, unlike glibc's, needs extensions to link libpython.
	# The runpath of Termux's own builds finds libQt6Pdf; tools/build_rootfs.py
	# retargets it like theirs.
	$CXX -shared -nostdlib++ -Wl,--as-needed -Wl,--version-script="$GEN/$mod.exp" \
		-Wl,-rpath,/data/data/com.termux/files/usr/lib "$GEN"/*.o -L"$PREFIX_TREE/lib" \
		-lQt6PdfWidgets -lQt6Pdf -lQt6Widgets -lQt6Gui -lQt6Core -lpython"$PYVER" -lc++_shared \
		-o "$SITE/PyQt6/$mod.abi3.so"
	"$BIN/llvm-strip" "$SITE/PyQt6/$mod.abi3.so"
	echo "built $SITE/PyQt6/$mod.abi3.so"
done
