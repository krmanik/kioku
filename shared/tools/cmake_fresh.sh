#!/bin/bash
# Forget a CMake build directory's cache when it was configured with another
# Qt: qt-cmake keeps the cached CMAKE_TOOLCHAIN_FILE, so after QT_VERSION
# moved (shared/versions.env) the app still linked the old Qt.
# Usage: cmake_fresh.sh <build dir> <Qt prefix it must use>
set -euo pipefail
CACHE=$1/CMakeCache.txt
[ -f "$CACHE" ] || exit 0
if ! grep -q "^CMAKE_TOOLCHAIN_FILE:FILEPATH=$2/" "$CACHE"; then
    echo "$1 was configured with another Qt; configuring again"
    rm -rf "$CACHE" "$1/CMakeFiles"
fi
