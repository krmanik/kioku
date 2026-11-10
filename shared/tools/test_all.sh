#!/bin/bash
# Every automated test of the native apps, without anyone at the keyboard:
# host tests (shared/tests/run.sh), then the in-app tests and the crash sweep
# (shared/tools/apptest.py) on each target that is available.
#
#   shared/tools/test_all.sh                 # host + every target found
#   shared/tools/test_all.sh android ios-sim # only these
#   KIOKU_BUILD=1 shared/tools/test_all.sh   # build and install first
#
# Targets: host, android (the emulator or phone adb sees; ANDROID_SERIAL picks
# one), ios-sim (KIOKU_SIM: name or UDID, default the booted one, else the
# first iPhone simulator), ios (a connected iPhone; KIOKU_DEVICE, KIOKU_TEAM
# for KIOKU_BUILD). Without targets: host, android when adb sees a device,
# ios-sim when Kioku is installed on a simulator, ios when an iPhone is
# connected. Reports: build/test-reports/. Exit status 1 when anything failed.
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
ADB=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}/platform-tools/adb
EXTRA=${KIOKU_APPTEST_ARGS:-}

targets=("$@")
if [ ${#targets[@]} -eq 0 ]; then
    targets=(host)
    "$ADB" get-state > /dev/null 2>&1 && targets+=(android)
    if command -v xcrun > /dev/null; then
        sim=$(xcrun simctl list devices booted | grep -oE '[0-9A-F-]{36}' | head -1)
        if [ -n "$sim" ] && xcrun simctl get_app_container "$sim" io.ankidesk.kioku > /dev/null 2>&1; then
            targets+=(ios-sim)
        fi
        xcrun devicectl list devices 2>/dev/null | grep -q 'connected' && targets+=(ios)
    fi
fi
echo "targets: ${targets[*]}"

declare -a summary
status=0
for t in "${targets[@]}"; do
    echo
    echo "################ $t"
    rc=0
    case $t in
    host)
        shared/tests/run.sh -q || rc=$?
        ;;
    android)
        if [ -n "${KIOKU_BUILD:-}" ]; then android/tools/run_device.sh 45 > /dev/null || rc=$?; fi
        [ $rc = 0 ] && { python3 -I shared/tools/apptest.py android ${ANDROID_SERIAL:+--device "$ANDROID_SERIAL"} $EXTRA || rc=$?; }
        ;;
    ios-sim)
        if [ -n "${KIOKU_BUILD:-}" ]; then ios/tools/run_sim.sh 45 > /dev/null || rc=$?; fi
        [ $rc = 0 ] && { python3 -I shared/tools/apptest.py ios-sim ${KIOKU_SIM:+--device "$KIOKU_SIM"} $EXTRA || rc=$?; }
        ;;
    ios)
        if [ -n "${KIOKU_BUILD:-}" ]; then ios/tools/run_device.sh 45 > /dev/null || rc=$?; fi
        [ $rc = 0 ] && { python3 -I shared/tools/apptest.py ios ${KIOKU_DEVICE:+--device "$KIOKU_DEVICE"} $EXTRA || rc=$?; }
        ;;
    *)
        echo "unknown target $t (host, android, ios-sim, ios)"; rc=2 ;;
    esac
    summary+=("$t: $([ $rc = 0 ] && echo passed || echo "FAILED ($rc)")")
    [ $rc = 0 ] || status=1
done

echo
echo "################ summary"
printf '  %s\n' "${summary[@]}"
exit $status
