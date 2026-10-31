#!/bin/bash
# Tests for the desktop image (desktop/README.md): starts it with a fresh
# /config and the test add-on (addon/), then drives Anki through the
# browser (browser.mjs) and through the add-on. Needs Docker, Node (npm ci
# here first) and Chrome: CHROME=path (chrome-headless-shell decodes no
# video, so its stream stays blank), or CHROME_URL for a Chrome started with
# --remote-debugging-port, to watch the tests (it must reach PORT..PORT+11).
#   IMAGE=name       test this image instead of building kioku-desktop:test
#   PORT=3000        host port for the container's 3000 (and PORT+1 for 3001)
#   SHOTS=folder     screenshots (default: shots/ here)
#   ARM64=1          also build for arm64 (QEMU) and import Anki's Qt there
#   KEEP=1           leave the container running at the end
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
IMAGE=${IMAGE:-}
PORT=${PORT:-3000}
SHOTS=${SHOTS:-$here/shots}
NAME=kioku-desktop-test
PASS=test-password
work=$(mktemp -d)
cfg=$work/config
mkdir -p "$SHOTS" "$cfg/Anki2/addons21" "$cfg/test"
cp -r "$here/addon" "$cfg/Anki2/addons21/kioku_desktop_test"

fails=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1"; fails=$((fails + 1)); }
check() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

# Python on Anki's main thread (addon/__init__.py); prints out.json
py() {
    rm -f "$cfg/test/out.json"
    printf '%s\n' "$1" > "$cfg/test/cmd.py"
    for _ in $(seq 600); do
        [ -f "$cfg/test/out.json" ] && { cat "$cfg/test/out.json"; return; }
        sleep 0.1
    done
    echo '{"error": "no answer from the test add-on"}'
}
# a field of py's output
field() { python3 -c 'import json,sys; v=json.load(sys.stdin).get(sys.argv[1]); print(v if v is not None else "")' "$1"; }
# wait for the Nth "open" event in events.log
opened() {
    for _ in $(seq 900); do
        [ "$(cat "$cfg/test/events.log" 2>/dev/null | grep -c ' open$')" -ge "$1" ] && return 0
        sleep 0.1
    done
    return 1
}
browser() { (cd "$here" && SHOTS=$SHOTS PASSWORD=$PASS URL=${URL:-http://localhost:$PORT/} node browser.mjs "$@"); }
start() {
    docker run -d --name $NAME --shm-size=1g \
        -p 127.0.0.1:$PORT:3000 -p 127.0.0.1:$((PORT + 1)):3001 \
        -e PUID="$(id -u)" -e PGID="$(id -g)" -e TZ=Asia/Kolkata \
        -e CUSTOM_USER=anki -e PASSWORD=$PASS -e ANKI_FIT_SCREEN=true \
        -e SELKIES_DESKTOP=true -e ANKI_MS_FONTS=true \
        -v "$cfg:/config" "$IMAGE" >/dev/null
    for _ in $(seq 120); do
        [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:$PORT/)" = 401 ] && return 0
        sleep 1
    done
    return 1
}
cleanup() {
    [ -n "${KEEP:-}" ] || docker rm -f $NAME kioku-desktop-nginx kioku-desktop-caddy >/dev/null 2>&1
    docker run --rm -v "$work:/w" alpine rm -rf /w/config >/dev/null 2>&1
    rm -rf "$work"
}
trap cleanup EXIT
docker rm -f $NAME kioku-desktop-nginx kioku-desktop-caddy >/dev/null 2>&1

if [ -z "$IMAGE" ]; then
    IMAGE=kioku-desktop:test
    source "$here/../../shared/versions.env"
    docker build -q --build-arg ANKI_PY_VERSION="$ANKI_PY_VERSION" -t $IMAGE "$here/.." >/dev/null || { echo "FAIL build"; exit 1; }
    ok "build"
fi

check "container starts, web page answers" start
# ANKI_MS_FONTS: downloaded into /config before the desktop starts
fonts() {
    for _ in $(seq 600); do
        [ -f "$cfg/.local/share/fonts/msttcorefonts/arial.ttf" ] && return 0
        sleep 1
    done
    return 1
}
check "Microsoft fonts downloaded into /config" fonts

# logging in
code() { curl -sk -o /dev/null -w '%{http_code}' "$@"; }
check "no password: 401" '[ "$(code http://localhost:$PORT/)" = 401 ]'
check "wrong password: 401" '[ "$(code -u anki:nope http://localhost:$PORT/)" = 401 ]'
check "password: 200" '[ "$(code -u anki:$PASS http://localhost:$PORT/)" = 200 ]'
check "https port, password: 200" '[ "$(code -u anki:$PASS https://localhost:$((PORT + 1))/)" = 200 ]'

# first run: the stream shows Anki's language window; from the browser's
# keyboard, Enter takes the selected language and Alt+Y confirms it, and
# the first profile opens (a click on the empty desktop focuses the page)
check "browser: stream shows the first-run window, keys answer it" \
    'browser "[[\"painted\"],[\"shot\",\"1-first-run\"],[\"click\",20,20],[\"key\",\"Enter\"],[\"wait\",1500],[\"key\",\"Alt+y\"],[\"wait\",3000]]" >/dev/null'
check "profile opens after the browser's keys" 'opened 1'
sleep 3

out=$(py 'import sys, aqt, anki.buildinfo
from aqt.qt import QT_VERSION_STR, QFontDatabase
out.update(anki=anki.buildinfo.version, python=sys.version.split()[0], qt=QT_VERSION_STR,
    profile=mw.pm.name, state=mw.state, path=mw.col.path,
    deckbrowser="deck-browser" in mw.web.page().url().toString() or mw.web.page().url().toString(),
    players=[type(p).__name__ for p in __import__("aqt.sound", fromlist=["x"]).av_player.players],
    arial="Arial" in QFontDatabase.families(), webdings="Webdings" in QFontDatabase.families())')
echo "     $out"
source "$here/../../shared/versions.env"
check "Anki $ANKI_TAG" '[ "$(echo "$out" | field anki)" = "$ANKI_TAG" ]'
check "collection on /config" '[[ "$(echo "$out" | field path)" == /config/Anki2/* ]]'
check "main window shows the deck list" '[ "$(echo "$out" | field state)" = deckBrowser ]'
check "mpv plays sound" '[[ "$(echo "$out" | field players)" == *Mpv* ]]'
check "Anki has Arial and Webdings" '[ "$(echo "$out" | field arial)$(echo "$out" | field webdings)" = TrueTrue ]'
check "Arial Greek falls back to Arial" \
    '[ "$(docker exec -u abc -e HOME=/config $NAME fc-match -f "%{family}" "Arial Greek")" = Arial ]'
check "font installers removed after installing" '[ ! -e "$cfg/.cache/anki-ms-fonts" ]'
check "SELKIES_DESKTOP: taskbar running" 'docker exec $NAME pgrep -f selkies-desktop >/dev/null'
check "one anki-session" '[ "$(docker exec $NAME pgrep -fc "^/bin/bash /usr/local/bin/anki-session")" = 1 ]'

# a note with media
out=$(py 'import io, math, struct, wave
b = io.BytesIO()
with wave.open(b, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
    w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 4))) for i in range(16000)))
name = mw.col.media.write_data("kioku-tone.wav", b.getvalue())
n = mw.col.new_note(mw.col.models.by_name("Basic"))
n["Front"] = "記憶 kioku [sound:%s]" % name
n["Back"] = "memory"
mw.col.add_note(n, mw.col.decks.id("Default"))
mw.reset()
out.update(notes=mw.col.note_count(), media=name)')
check "add a note with a sound" '[ "$(echo "$out" | field notes)" = 1 ]'

# playing it reaches the container's sound server (streamed to the browser)
py 'from aqt.sound import av_player
from anki.sound import SoundOrVideoTag
av_player.play_tags([SoundOrVideoTag("kioku-tone.wav")])' >/dev/null
sleep 0.7
check "sound plays into PulseAudio" \
    '[ -n "$(docker exec -u abc -e XDG_RUNTIME_DIR=/config/.XDG $NAME pactl list short sink-inputs 2>/dev/null)" ]'

# mouse and keyboard from the browser: a full-screen dialog with a text box
# at the top and a button filling the rest
py 'from aqt.qt import QDialog, QLineEdit, QPushButton, QVBoxLayout
d = QDialog(mw); l = QVBoxLayout(d)
d.edit = QLineEdit(); l.addWidget(d.edit)
b = QPushButton("Click"); b.setMinimumHeight(500); l.addWidget(b)
b.clicked.connect(lambda: setattr(mw, "_kioku_test", d.edit.text()) or d.accept())
mw._kioku_test = None; d.showFullScreen(); d.edit.setFocus()' >/dev/null
browser '[["wait",1500],["type","hello kioku"],["shot","2-typing"],["click",640,600],["wait",1500]]' >/dev/null
out=$(py 'out["text"] = mw._kioku_test')
check "browser typing and clicking reach Anki" '[ "$(echo "$out" | field text)" = "hello kioku" ]'

# only the main window is maximized; dialogs (Create Deck, ...) keep their size
py 'from aqt.qt import QInputDialog
d = QInputDialog(mw); d.setWindowTitle("Create Deck"); d.show(); mw._kioku_dialog = d' >/dev/null
sleep 2
out=$(py 'd = mw._kioku_dialog
out.update(main=mw.isMaximized(), dialog=d.isMaximized(), width=d.width()); d.close()')
echo "     $out"
check "main window maximized" '[ "$(echo "$out" | field main)" = True ]'
check "dialogs not maximized" '[ "$(echo "$out" | field dialog)" = False ]'

# files from the browser's computer: a deck uploaded through the page lands
# in ~/Desktop, where Anki's open dialogs start; exports are saved there by
# default and download from the page's Files panel
docker exec -u abc $NAME /opt/anki/bin/python -c '
from anki.collection import Collection, ExportAnkiPackageOptions
from anki.import_export_pb2 import ExportLimit
import os
os.makedirs("/tmp/deck", exist_ok=True)
col = Collection("/tmp/deck/collection.anki2")
n = col.new_note(col.models.by_name("Basic")); n["Front"] = "uploaded"; col.add_note(n, 1)
col.export_anki_package(out_path="/config/test/shared-deck.apkg", options=ExportAnkiPackageOptions(with_scheduling=False, with_deck_configs=False, with_media=True, legacy=False), limit=ExportLimit())
col.close()'
mv "$cfg/test/shared-deck.apkg" "$work/shared-deck.apkg"
browser "[[\"upload\",\"$work/shared-deck.apkg\"],[\"wait\",4000]]" >/dev/null
check "upload from the browser lands in ~/Desktop" 'cmp -s "$work/shared-deck.apkg" "$cfg/Desktop/shared-deck.apkg"'
out=$(py 'import os
from aqt.qt import QStandardPaths
from anki.import_export_pb2 import ImportAnkiPackageRequest
out.update(cwd=os.getcwd(), docs=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
mw.col.import_anki_package(ImportAnkiPackageRequest(package_path=os.path.join(out["cwd"], "shared-deck.apkg")))
out.update(notes=mw.col.note_count())
from anki.collection import ExportAnkiPackageOptions
from anki.import_export_pb2 import ExportLimit
mw.col.export_anki_package(out_path=os.path.join(out["docs"], "export.apkg"), options=ExportAnkiPackageOptions(with_scheduling=True, with_deck_configs=True, with_media=True, legacy=False), limit=ExportLimit())
mw.reset()')
echo "     $out"
check "open dialogs start in ~/Desktop" '[ "$(echo "$out" | field cwd)" = /config/Desktop ]'
check "save dialogs start in ~/Desktop" '[ "$(echo "$out" | field docs)" = /config/Desktop ]'
check "import the uploaded deck" '[ "$(echo "$out" | field notes)" = 2 ]'
curl -s -u anki:$PASS -o "$work/export.apkg" "http://localhost:$PORT/api/files/export.apkg"
check "download an export from the Files panel" 'cmp -s "$work/export.apkg" "$cfg/Desktop/export.apkg"'

# windows, at desktop and phone sizes
py 'mw.onBrowse()' >/dev/null
browser '[["wait",3000],["painted"],["shot","3-browse"]]' >/dev/null
out=$(py 'import aqt
b = aqt.dialogs._dialogs["Browser"][1]
out.update(rows=b.table.len() if b else None); b and b.close()')
check "Browse shows the notes" '[ "$(echo "$out" | field rows)" = 2 ]'
check "desktop-size screen: pages at 100%" '[ "$(py "out[\"z\"] = mw.web.zoomFactor()" | field z)" = 1.0 ]'
# ANKI_FIT_SCREEN: on a phone the pages zoom out and Browse fills the screen
# (the browser stays connected meanwhile: the screen is its size)
VIEWPORT=430x932 browser '[["wait",3000],["painted"],["shot","4-phone"],["wait",8000],["shot","5-phone-browse"]]' >/dev/null &
phone=$!
sleep 9
py 'mw.onBrowse()' >/dev/null
sleep 2
out=$(py 'import aqt
from aqt.qt import QGuiApplication
b = aqt.dialogs._dialogs["Browser"][1]
out.update(screen=QGuiApplication.primaryScreen().availableGeometry().width(),
    zoom=round(mw.web.zoomFactor(), 2), browse=b.isMaximized())')
echo "     $out"
check "phone-size browser" 'wait $phone'
check "phone: pages zoomed out to fit" 'python3 -c "import json,sys; z=json.loads(sys.argv[1])[\"zoom\"]; sys.exit(not 0 < z < 1)" "$out"'
check "phone: Browse fills the screen" '[ "$(echo "$out" | field browse)" = True ]'
py 'import aqt; b = aqt.dialogs._dialogs["Browser"][1]; b and b.close()' >/dev/null

# sync with a sync server (Anki's own, run in the container)
docker exec -d -u abc -e SYNC_USER1=test:pass -e SYNC_PORT=27701 -e SYNC_BASE=/config/test/sync \
    $NAME /opt/anki/bin/python -m anki.syncserver
sleep 3
py 'mw.pm.set_custom_sync_url("http://127.0.0.1:27701/")
auth = mw.col.sync_login("test", "pass", "http://127.0.0.1:27701/")
mw.pm.set_sync_key(auth.hkey); mw.pm.set_sync_username("test")
mw.on_sync_button_clicked()' >/dev/null
# the server has nothing yet: Anki asks to replace it, answered from the browser
browser '[["wait",3000],["shot","6-sync-question"],["key","Alt+y"],["wait",3000]]' >/dev/null
for _ in $(seq 60); do [ -f "$cfg/test/sync/test/collection.anki2" ] && [ -f "$cfg/test/sync/test/media/kioku-tone.wav" ] && break; sleep 1; done
# the server keeps its collection locked; without it, no syncing on close
docker exec $NAME pkill -f anki.syncserver
py 'mw.pm.profile["autoSync"] = False' >/dev/null
sleep 1
echo "     sync: $(ls "$cfg/test/sync/test" "$cfg/test/sync/test/media" 2>&1 | tr '\n' ' ')"
check "sync uploads the collection and its media" \
    'python3 -c "import sqlite3,sys; sys.exit(sqlite3.connect(\"$cfg/test/sync/test/collection.anki2\").execute(\"select count() from notes\").fetchone()[0] != 2)" && [ -f "$cfg/test/sync/test/media/kioku-tone.wav" ]'

# quitting Anki opens it again
py 'from aqt.qt import QTimer; QTimer.singleShot(200, mw.close)' >/dev/null
check "Anki opens again after File > Exit" 'opened 2'
sleep 3

# docker stop closes the collection; data survives a new container
t=$(date +%s)
docker stop -t 90 $NAME >/dev/null
check "docker stop within 30 s" '[ $(( $(date +%s) - t )) -lt 30 ]'
check "docker stop closes the profile" '[ "$(tail -1 "$cfg/test/events.log" | cut -d" " -f3)" = close ]'
check "collection closed cleanly (no -wal left)" '[ ! -e "$cfg/Anki2/User 1/collection.anki2-wal" ]'
check "a backup on the server" '[ -n "$(ls "$cfg/Anki2/User 1/backups" 2>/dev/null)" ]'
docker rm $NAME >/dev/null
check "new container starts" start
check "profile opens by itself" 'opened 3'
sleep 2
out=$(py 'out.update(notes=mw.col.note_count(), media=mw.col.media.have("kioku-tone.wav"))')
check "notes and media kept" '[ "$(echo "$out" | field notes)" = 2 ] && [ "$(echo "$out" | field media)" = True ]'

# reverse proxies (plain http on localhost, which browsers treat as secure)
cat > "$work/nginx.conf" <<EOF
server {
    listen $((PORT + 10));
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 1h;
        proxy_buffering off;
    }
}
EOF
docker run -d --name kioku-desktop-nginx --network host -v "$work/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.29-alpine >/dev/null
docker run -d --name kioku-desktop-caddy --network host caddy:2 caddy reverse-proxy --from :$((PORT + 11)) --to 127.0.0.1:$PORT >/dev/null
sleep 3
check "through nginx" 'URL=http://localhost:$((PORT + 10))/ browser "[[\"painted\"]]" >/dev/null'
check "through Caddy" 'URL=http://localhost:$((PORT + 11))/ browser "[[\"painted\"],[\"shot\",\"5-caddy\"]]" >/dev/null'

if [ -n "${ARM64:-}" ]; then
    docker buildx build -q --platform linux/arm64 --build-arg ANKI_PY_VERSION="$ANKI_PY_VERSION" \
        -t kioku-desktop:test-arm64 --load "$here/.." >/dev/null
    check "arm64: Anki and Qt WebEngine import" \
        'docker run --rm --platform linux/arm64 --entrypoint /opt/anki/bin/python kioku-desktop:test-arm64 -c "import aqt, PyQt6.QtWebEngineWidgets, anki.collection" '
fi

echo "screenshots: $SHOTS"
[ $fails = 0 ] && echo "all passed" || echo "$fails failed"
exit $((fails > 0))
