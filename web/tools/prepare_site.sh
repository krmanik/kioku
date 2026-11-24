#!/bin/bash
# Anki's Python packages and their dependencies for the wasm file system:
# the site-packages the Kioku repository assembles for iOS
# (shared/tools/prepare_site.sh), minus the iOS-only rubicon and PyMuPDF
# (its native modules are linked into the iOS app only), and minus what
# ios/tools/build.sh adds for add-ons in the native apps: the programs'
# data (kioku_programs_data) and the native packages of
# shared/tools/build_wheels.sh (iOS builds; jieba goes with them, 37 MB).
# They took kioku.data past Cloudflare's 25 MiB per file. orjson's and
# markupsafe's native halves are linked in (build_orjson.sh, CMakeLists.txt).
set -euo pipefail
source "$(dirname "$0")/env.sh"
rsync -a --delete --delete-excluded --exclude __pycache__ --exclude 'rubicon*' \
    --exclude pymupdf --exclude fitz \
    --exclude kioku_programs_data --exclude '_cffi_backend*' \
    --exclude cffi --exclude 'cffi-*' --exclude pycparser --exclude 'pycparser-*' \
    --exclude cryptography --exclude 'cryptography-*' \
    --exclude OpenSSL --exclude 'pyopenssl-*' --exclude numpy --exclude 'numpy-*' \
    --exclude PIL --exclude 'pillow-*' --exclude jieba --exclude 'jieba-*' \
    "$KIOKU_REPO/ios/build/site/" "$ROOT/build/site/"
# urllib3 takes sys.platform == "emscripten" for Pyodide and imports its
# `js` module; without Pyodide, keep its plain (socket) connections
python3 - "$ROOT/build/site/urllib3/__init__.py" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
old = '''if sys.platform == "emscripten":
    from .contrib.emscripten import inject_into_urllib3  # noqa: 401

    inject_into_urllib3()'''
new = '''if sys.platform == "emscripten":
    # kioku web: no Pyodide `js` module; plain sockets (emscripten's) instead
    try:
        from .contrib.emscripten import inject_into_urllib3  # noqa: 401
    except ImportError:
        pass
    else:
        inject_into_urllib3()'''
if old in s:
    open(p, "w").write(s.replace(old, new))
PY
