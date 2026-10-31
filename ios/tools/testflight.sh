#!/bin/bash
# Build Kioku for the App Store and upload it to TestFlight.
#
#   KIOKU_TEAM=<team id> tools/testflight.sh                build, archive, upload
#   KIOKU_TEAM=<team id> tools/testflight.sh --upload-only  upload the last archive
#   KIOKU_TEAM=<team id> tools/testflight.sh --archive-only build and archive only
#                                                         (upload from Xcode's Organizer)
#
# Signs with your team's distribution certificate through Xcode's automatic
# signing, authenticated with an App Store Connect API key (no Xcode sign-in):
#   APP_STORE_KEY_ID, APP_STORE_ISSUER_ID   from the environment or ../.env
#   APP_STORE_KEY_PATH                      default ../AuthKey_<key id>.p8
# The app (bundle id io.ankidesk.kioku) must exist in App Store Connect.
# Env: KIOKU_VERSION (default: the latest v* tag), KIOKU_BUILD (default: the
# number of commits; must grow with every upload of the same version)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
TEAM=${KIOKU_TEAM:?set KIOKU_TEAM to your Apple team id}
for var in APP_STORE_KEY_ID APP_STORE_ISSUER_ID; do
    if [ -z "${!var:-}" ] && [ -f "$ROOT/../.env" ]; then
        export "$var=$(sed -n "s/^$var=//p" "$ROOT/../.env" | tr -d "\"'")"
    fi
    [ -n "${!var:-}" ] || { echo "$var is not set" >&2; exit 1; }
done
KEY=${APP_STORE_KEY_PATH:-$ROOT/../AuthKey_$APP_STORE_KEY_ID.p8}
[ -f "$KEY" ] || { echo "API key not found: $KEY" >&2; exit 1; }
KEY=$(cd "$(dirname "$KEY")" && pwd)/$(basename "$KEY")
TAG=$(git -C "$ROOT" describe --tags --abbrev=0 --match 'v*' 2>/dev/null || echo "v$ANKI_PY_VERSION")
VERSION=${KIOKU_VERSION:-${TAG#v}}
BUILD_NUMBER=${KIOKU_BUILD:-$(git -C "$ROOT" rev-list --count HEAD)}
QT=$ROOT/deps/qt/$QT_VERSION
OUT=$ROOT/build/testflight
AUTH=(-allowProvisioningUpdates -authenticationKeyPath "$KEY"
      -authenticationKeyID "$APP_STORE_KEY_ID" -authenticationKeyIssuerID "$APP_STORE_ISSUER_ID")

if [ "${1:-}" != --upload-only ]; then
    "$ROOT/tools/fetch_deps.sh"
    "$ROOT/tools/build_qt_plugin.sh"
    "$ROOT/tools/build_rust.sh" aarch64-apple-ios
    "$ROOT/tools/gen_pyqt.sh" > /dev/null
    "$ROOT/../shared/tools/prepare_site.sh" "$ROOT/.venv/bin/python" "$ROOT/deps/sdist" "$ROOT/build/site"
    # the same extras as tools/build.sh
    "$ROOT/../shared/tools/build_pymupdf.sh" ios > "$ROOT/build/pymupdf.log" 2>&1 || {
        tail -30 "$ROOT/build/pymupdf.log"; exit 1; }
    rsync -a "$ROOT/../build/pymupdf/ios/site/" "$ROOT/build/site/"
    "$ROOT/../shared/tools/build_programs.sh" ios > "$ROOT/build/programs.log" 2>&1 || {
        tail -30 "$ROOT/build/programs.log"; exit 1; }
    rsync -a --delete "$ROOT/../build/programs/data/" "$ROOT/build/site/kioku_programs_data/"
    "$ROOT/../shared/tools/build_wheels.sh" ios > "$ROOT/build/wheels.log" 2>&1 || {
        tail -30 "$ROOT/build/wheels.log"; exit 1; }
    rsync -a "$ROOT/../build/wheels/ios/site/" "$ROOT/build/site/"

    "$QT/ios/bin/qt-cmake" -S "$ROOT" -B "$ROOT/build/xcode-dist" -G Xcode \
        -DQT_HOST_PATH="$QT/macos" -DCMAKE_OSX_SYSROOT=iphoneos -DCMAKE_OSX_ARCHITECTURES=arm64 \
        -DKIOKU_TEAM="$TEAM" -DKIOKU_VERSION="$VERSION" -DKIOKU_BUILD="$BUILD_NUMBER" > /dev/null

    rm -rf "$OUT" && mkdir -p "$OUT"
    echo "Archiving Kioku $VERSION ($BUILD_NUMBER)"
    xcodebuild archive -project "$ROOT/build/xcode-dist/Kioku.xcodeproj" -scheme Kioku \
        -configuration Release -destination generic/platform=iOS \
        -archivePath "$OUT/Kioku.xcarchive" "${AUTH[@]}" > "$ROOT/build/xcode-archive.log" 2>&1 || {
        grep -E 'error:|^ld: |Undefined' "$ROOT/build/xcode-archive.log" | sort -u | head -40
        exit 1
    }
fi
if [ "${1:-}" = --archive-only ]; then
    echo "Archived $OUT/Kioku.xcarchive"
    exit 0
fi

cat > "$OUT/ExportOptions.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store-connect</string>
    <key>destination</key>
    <string>upload</string>
    <key>teamID</key>
    <string>$TEAM</string>
    <key>signingStyle</key>
    <string>automatic</string>
    <key>manageAppVersionAndBuildNumber</key>
    <false/>
</dict>
</plist>
EOF
echo "Uploading to App Store Connect"
xcodebuild -exportArchive -archivePath "$OUT/Kioku.xcarchive" \
    -exportOptionsPlist "$OUT/ExportOptions.plist" -exportPath "$OUT" \
    "${AUTH[@]}" > "$ROOT/build/xcode-upload.log" 2>&1 || {
    grep -iE 'error|failed' "$ROOT/build/xcode-upload.log" | sort -u | head -40
    exit 1
}
echo "Uploaded Kioku $VERSION ($BUILD_NUMBER). It shows up in TestFlight after Apple processes it."
