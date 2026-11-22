#!/bin/bash
# Emscripten 4.0.7 (the version Qt 6.11's wasm libraries are built with) and
# Qt for WebAssembly (multithread, QT_VERSION) into deps/. Host Qt comes from the
# Kioku repository's iOS build (tools/env.sh).
set -euo pipefail
source "$(dirname "$0")/env.sh"
mkdir -p "$ROOT/deps"
cd "$ROOT/deps"
if [ ! -d emsdk ]; then
    git clone -q --depth 1 https://github.com/emscripten-core/emsdk.git
    emsdk/emsdk install 4.0.7
    emsdk/emsdk activate 4.0.7
fi
if [ ! -d "qt/$QT_VERSION/wasm_multithread" ]; then
    uvx --from aqtinstall aqt install-qt all_os wasm "$QT_VERSION" wasm_multithread -O qt \
        -b https://mirrors.ocf.berkeley.edu/qt/
fi
ln -sfn "$KIOKU_REPO/ios/deps/qt/$QT_VERSION/macos" "qt/$QT_VERSION/macos"
# aqt's qmake wrapper calls host qmake relative to the current directory
sed -i '' "s#^qt/$QT_VERSION/macos/bin/qmake6#\"\$script_dir_path/../../macos/bin/qmake6\"#" \
    "qt/$QT_VERSION/wasm_multithread/bin/qmake"
# Fallback fonts for the scripts Qt's own fonts (DejaVu) lack, packed into
# kioku.data (kioku_platform._add_fonts): Chinese and Japanese, Korean,
# Thai, Oriya (Anki's language list) and Devanagari
mkdir -p fonts
CJK=https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/SubsetOTF
NOTO=https://github.com/notofonts/notofonts.github.io/raw/42af67ccd12bc0e31ed85384bf73e39248265374/fonts
while read -r sum url; do
    [ -f "fonts/${url##*/}" ] || curl -fsSL -o "fonts/${url##*/}" "$url"
    echo "$sum  fonts/${url##*/}" | shasum -a 256 -c --quiet
done <<EOF
faa6c9df652116dde789d351359f3d7e5d2285a2b2a1f04a2d7244df706d5ea9 $CJK/SC/NotoSansSC-Regular.otf
69975a0ac8472717870aefeab0a4d52739308d90856b9955313b2ad5e0148d68 $CJK/KR/NotoSansKR-Regular.otf
61cf814eec46b294d6ea4401ac295d0cecd5207bd2331dcc5a15e7301d30ee44 $NOTO/NotoSansThai/hinted/ttf/NotoSansThai-Regular.ttf
a16645d056017927406546aa78e4ce15e782fd8783467267b75450453d007415 $NOTO/NotoSansOriya/hinted/ttf/NotoSansOriya-Regular.ttf
4e3c66638958c3e2ab5d37f47a8deb89fffeb7be9985c665a519bbc7ba762313 $NOTO/NotoSansDevanagari/hinted/ttf/NotoSansDevanagari-Regular.ttf
EOF
# IANA time zones (Python's tzdata package, packed as /site/tzdata):
# kioku_platform._set_timezone() gives Anki's Rust core the browser's zone
if [ ! -d tzdata ]; then
    curl -fsSL -o tzdata.whl https://files.pythonhosted.org/packages/94/21/1e5995a1c920cce14e4bffae20c665ec10e7ed03ab25e006cd741092b718/tzdata-2026.5-py2.py3-none-any.whl
    echo "b683bd1b6659ddcd810ff02ad09ba821d4bf1065072805063eb35c49617905ac  tzdata.whl" | shasum -a 256 -c --quiet
    unzip -q tzdata.whl 'tzdata/*' -d .
    rm tzdata.whl
fi
