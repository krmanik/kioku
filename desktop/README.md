# Anki desktop on a server, in the browser (Docker)

`ghcr.io/krmanik/kioku-desktop` runs the real Anki desktop app, unmodified
from PyPI, on your server or NAS and shows it in any browser. Anki, its
Python, your add-ons and your collection all stay on the server: the
browser only receives a video of the screen (and the sound) and sends back
the keyboard and mouse, so a large collection is never downloaded or copied
anywhere ([issue #5](https://github.com/krmanik/kioku/issues/5)). How to run it:
the manual's [Self-hosted server](../docs/manual/src/install/self-hosted.md).

```
Browser                                Container (LinuxServer Selkies base)
───────                                ────────────────────────────────────
video, sound ◀── WebSocket ─────────── Selkies: labwc (Wayland) screen, PulseAudio
keyboard, mouse, clipboard ──────────▶ anki-session ─ Anki (aqt, Qt 6, mpv)
Upload / Files panel ◀───────────────▶ /config/Desktop
                                       /config/Anki2: profiles, collections,
                                         media, add-ons, backups
```

## What's in the image

- **Base:** `ghcr.io/linuxserver/baseimage-selkies:debiantrixie`: nginx
  with basic auth (`CUSTOM_USER`/`PASSWORD`) on 3000 (http, for a reverse
  proxy) and 3001 (https, self-signed), the Selkies streaming server and web
  client, labwc, PulseAudio, s6. Its own settings (resolution, encoders,
  touch, hardening) work as documented by LinuxServer.
- **Anki:** a venv in `/opt/anki` with `aqt[qt]==$ANKI_PY_VERSION`
  (`shared/versions.env`), the same wheels Anki's Linux launcher installs,
  plus Debian's `mpv` for sound, Noto CJK/emoji fonts and `libminizip`
  (the arm64 Qt WebEngine wheel links it; amd64's bundles its own).
- **`/usr/local/bin/anki-session`** (the autostart): runs
  `anki -b /config/Anki2` from `/config/Desktop` and opens it again if it's
  quit. A lock keeps it to one: with `SELKIES_DESKTOP`, the base's
  `startwm_wayland.sh` starts the taskbar a fixed second after labwc and
  starts the desktop again when labwc wasn't ready, and the first labwc's
  autostart can outlive it; a second loop would start Anki every second,
  and each new Anki raises the running one's main window.
- **Stopping:** Anki handles TERM by closing the collection (and making its
  backup), but the base's `svc-de` finish sends TERM to the whole desktop at
  once and waits 5 s, and Qt exits at once when `svc-dbus` stops, so Anki
  would be gone first. The oneshot `anki-close` depends on both, so s6
  stops it first: its down script
  (`/usr/local/bin/anki-close`) stops `anki-session` and waits for Anki.
  The compose file's `stop_grace_period` allows a minute (`docker stop`
  waits 10 s by default; a large collection's backup can take longer).
- **`ANKI_FIT_SCREEN=true`** (`/usr/local/lib/kioku/anki_fit.py`, run
  instead of `anki`): when the screen (the browser's size) is narrower than
  800 pixels, Anki's pages are zoomed out to fit and windows bigger than the
  screen are maximized; it follows the screen as it changes. Wider screens
  are left as they are, View › Zoom included.
- **Files:** the browser's Upload (or a file dropped on the page) and Files
  panel use `/config/Desktop`. Anki's open dialogs start in the working
  folder and its save dialogs in Documents, so `anki-session` makes both
  `/config/Desktop`.
- **Windows:** LinuxServer's labwc template maximizes every window; the
  Dockerfile narrows that rule to the main window (`* - Anki`), so dialogs
  open at their normal size.
- `SELKIES_ENABLE_BINARY_CLIPBOARD=true`: images copied in the browser can
  be pasted into the editor and Image Occlusion.
- **`ANKI_MS_FONTS=true`** (s6-rc oneshot `init-anki-fonts`, before
  `svc-de`, running `/usr/local/bin/anki-ms-fonts` as `abc`): Microsoft's
  core fonts (Arial, Times New Roman, Verdana, ...), which shared decks
  such as AnKing name in their styling. Their licence allows passing them
  on only as Microsoft's own installers, so the image has none: on the
  first start they are downloaded from the corefonts project on
  SourceForge (in parallel: a mirror can take a minute for each file),
  checked against Debian's `ttf-mscorefonts-installer` sums, unpacked with
  `cabextract` into `/config/.local/share/fonts/msttcorefonts` (fontconfig
  reads it) and kept there, with "Arial Greek" (older decks) as an alias of
  Arial. SourceForge's mirrors sometimes reset connections, so each file is
  tried again within the start (curl `--retry-all-errors`, then up to two
  more rounds for the missing ones); installers that arrived wait in
  `/config/.cache/anki-ms-fonts`, and the next start fetches only the
  missing ones. `ANKI_MS_FONTS_URL` replaces the SourceForge address (a
  folder with the same `.exe` files).
- **Compose file:** `SELKIES_DESKTOP=true` (the base's taskbar, to switch
  between Anki's windows) and, commented out, `/dev/dri` for the server's
  GPU (the base then renders and encodes on it; without it everything is
  drawn by the CPU). Docker refuses to start a container whose device is
  missing, so it's left to servers that have one.

## Building and testing

```sh
source shared/versions.env
docker build --build-arg ANKI_PY_VERSION=$ANKI_PY_VERSION -t kioku-desktop desktop
cd desktop/test && npm ci && CHROME=/path/to/chrome ./run.sh
```

`test/run.sh` builds the image (or tests `IMAGE=`), starts it with a fresh
`/config` and a test add-on (`test/addon`, which runs Python sent by the
script on Anki's main thread), and drives it through headless Chrome
(`test/browser.mjs`): logging in, the first-run window seen in the stream
and answered with the browser's keyboard, typing and clicking, Browse,
a phone-size page (with `ANKI_FIT_SCREEN`: pages zoomed out, Browse
maximized), the Microsoft fonts downloaded and seen by Anki, the taskbar, sound reaching PulseAudio, dialogs not maximized,
uploading a deck from the browser and importing it, downloading an export,
syncing with Anki's sync server, quitting Anki, `docker stop` closing the
collection, the data in a new container, and nginx and Caddy in front.
`ARM64=1` also builds for arm64 and imports Anki there. Screenshots land in
`test/shots/`.

GitHub (`.github/workflows/desktop-docker.yml`, on a release or by hand):
builds, runs the tests on amd64, then pushes
`ghcr.io/krmanik/kioku-desktop:<Anki version>` and `:latest` for amd64 and
arm64.
