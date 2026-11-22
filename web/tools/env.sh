# Sourced by the tools: paths to web/ and to the Kioku repository around it
# (github.com/krmanik/kioku), which provides Anki's source and Rust core
# (ios/deps/anki), the shared kioku Python package (shared/python), the
# PyQt6 sdists and sip-build (ios/deps/sdist, ios/.venv), host Qt
# (ios/deps/qt/<ver>/macos) and the versions (shared/versions.env: Anki's
# Python, Qt and PyQt6). KIOKU_REPO overrides it.
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
KIOKU_REPO=${KIOKU_REPO:-$ROOT/..}
KIOKU_REPO=$(cd "$KIOKU_REPO" && pwd)
source "$KIOKU_REPO/shared/versions.env"
