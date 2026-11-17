<p align="center">
  <img src="shared/icon/kioku.svg" width="120" alt="Kioku icon">
</p>

<h1 align="center">Kioku</h1>

<p align="center">
  <b>The real Anki desktop app on your phone, in your browser and on your own server.</b><br>
  Add-ons, the card browser and every desktop feature, made for a touch screen.
</p>

<p align="center">
  <a href="https://github.com/krmanik/kioku/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/krmanik/kioku?label=version"></a>
  <img alt="Anki 26.09.3" src="https://img.shields.io/badge/Anki-26.09.3-2563EB">
  <img alt="iOS 17+" src="https://img.shields.io/badge/iOS-17%2B-000000?logo=apple&logoColor=white">
  <img alt="Android 7+" src="https://img.shields.io/badge/Android-7%2B-3DDC84?logo=android&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-amd64%20%7C%20arm64-2496ED?logo=docker&logoColor=white">
  <a href="https://github.com/krmanik/kioku/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/krmanik/kioku?style=flat"></a>
</p>

<p align="center">
  <a href="https://github.com/krmanik/kioku/releases/latest"><img alt="Download iOS" src="https://img.shields.io/github/v/release/krmanik/kioku?label=Download%20iOS&color=000000&labelColor=333333&style=for-the-badge&logo=apple&logoColor=white"></a>
  <a href="https://forms.gle/fw4YMTdGbgD8nqPe8"><img alt="iOS TestFlight beta" src="https://img.shields.io/badge/TestFlight-join%20beta-0D96F6?labelColor=333333&style=for-the-badge&logo=apple&logoColor=white"></a><br>
  <a href="https://github.com/krmanik/kioku/releases/latest"><img alt="Download Android (native)" src="https://img.shields.io/github/v/release/krmanik/kioku?label=Download%20Android&color=1E7F3C&labelColor=333333&style=for-the-badge&logo=android&logoColor=white"></a>
  <a href="https://github.com/krmanik/kioku/releases/latest"><img alt="Download Android (Termux)" src="https://img.shields.io/github/v/release/krmanik/kioku?label=Download%20Termux&color=2563EB&labelColor=333333&style=for-the-badge&logo=gnubash&logoColor=white"></a><br>
  <a href="https://kioku.krmanik.workers.dev"><img alt="Try in the browser (experimental)" src="https://img.shields.io/badge/Try-Web%20%C2%B7%20experimental-B45309?labelColor=333333&style=for-the-badge&logo=googlechrome&logoColor=white"></a>
  <a href="https://krmanik.github.io/kioku/install/self-hosted.html"><img alt="Self-host with Docker" src="https://img.shields.io/badge/Self--host-Docker-2496ED?labelColor=333333&style=for-the-badge&logo=docker&logoColor=white"></a>
</p>

<p align="center">
  <a href="https://krmanik.github.io/kioku/"><b>User manual</b></a> ·
  <a href="https://github.com/krmanik/kioku/releases/latest">Releases</a> ·
  <a href="docs/screenshots.md">Screenshots</a> ·
  <a href="https://github.com/krmanik/kioku/issues">Issues</a>
</p>

---

AnkiDroid and AnkiMobile are great, but some things exist only in Anki
desktop: add-ons, and the desktop's own card browser, editors and tools.
Kioku runs the **unmodified Anki desktop app** (`aqt`, Qt 6, Anki's Rust
core) wherever you are: as an app on your phone, in a browser tab, or on
your own server, used from any browser. (Kioku, 記憶, is Japanese for
"memory".)

## Pick a variant

| | Needs | Feels like | Your collection | Install |
| --- | --- | --- | --- | --- |
| **iPhone, iPad** | iOS 17+ (39 MB) | a phone app | on the device | [TestFlight, AltStore or sideload](https://krmanik.github.io/kioku/install/ios.html) |
| **Android, native** | Android 9+, arm64 (48 MB) | a phone app | on the device | [APK](https://krmanik.github.io/kioku/install/android.html) |
| **Android, Termux** | Android 7+, arm64, ~1 GB free, 3 GB+ RAM (235 MB) | a small Linux desktop | on the device | [APK](https://krmanik.github.io/kioku/install/termux.html) |
| **Web** *(experimental)* | a recent browser (~31 MB download) | Anki in a tab | in that browser | [open it](https://krmanik.github.io/kioku/install/web.html) |
| **Your server** *(Docker)* | amd64 or arm64 server, any browser | Anki desktop, streamed | on your server | [compose file](https://krmanik.github.io/kioku/install/self-hosted.html) |

All of them are the same Anki release and sync with each other through
AnkiWeb or a sync server. Not sure? See
[Which variant?](https://krmanik.github.io/kioku/variants.html)

<h3 align="center">iPhone and iPad</h3>
<p align="center">
  <img src="docs/images/strip-ios.png" alt="iPhone: deck list, reviewing a Chinese card, reviewing a NeetCode card and Browse">
</p>
<h3 align="center">Android, native</h3>
<p align="center">
  <img src="docs/images/strip-android.png" alt="Native Android: deck list, reviewing a Chinese card, Browse and Statistics">
</p>
<h3 align="center">Android, Termux</h3>
<p align="center">
  <img src="docs/images/strip-termux.png" alt="Termux variant: the Kioku desktop, the deck list, reviewing a card and the Software page">
</p>

More, including the web and server variants: [screenshots](docs/screenshots.md).

## Features

- **Anki desktop, unmodified**: Anki 26.09.3's own Python code and Rust
  core, with a thin layer that fits it to a phone.
- **Desktop add-ons** from AnkiWeb, installed inside the app.
- **Made for touch**: big type, drag to scroll, the keyboard opens on text
  fields, windows fit the phone in portrait and landscape.
- **Your data stays with you**: on the phone, in your browser or on your
  server. AnkiWeb sync, import and export work as usual.
- **The phone as a sync server** for AnkiDroid, Kioku and Anki on your
  computers, and **AnkiDroid's media folder** shared with a Kioku profile
  (Android).
- **Remote desktop**: the phone's Anki in a computer's browser (Termux).
- **Self-hosting**: a Docker image runs Anki desktop on your server or NAS,
  with your add-ons and a large collection, and streams it to any browser.

How to install and use it: the **[Kioku manual](https://krmanik.github.io/kioku/)**
(source in [docs/manual/](docs/manual/src/SUMMARY.md)). Everything about
Anki itself is in [Anki's manual](https://docs.ankiweb.net/).

## Repository

| Folder | What's in it |
| --- | --- |
| [`ios/`](ios/) | iOS variant: Xcode build, WKWebView layer ([README](ios/README.md)) |
| [`android/`](android/) | native Android variant: CMake/Gradle build, Android web view, Qt patches |
| [`termux/`](termux/) | Termux variant: Android app, desktop shell, runtime build ([README](termux/README.md)) |
| [`web/`](web/) | web variant: Anki compiled to WebAssembly, Cloudflare hosting ([README](web/README.md)) |
| [`desktop/`](desktop/) | Docker image: Anki desktop on a server, streamed to the browser ([README](desktop/README.md)) |
| [`shared/`](shared/) | shared by the native variants: Python layer, versions, icon, patches, build tools |
| [`docs/`](docs/) | [user manual](docs/manual/), [fixes log](docs/fixes.md), [test results](docs/testing.md), [privacy](docs/privacy.md) |

## Building

| Variant | Build | Tests |
| --- | --- | --- |
| iOS | `cd ios && tools/build.sh` ([ios/README.md](ios/README.md)) | `shared/tests/run.sh` (the Python layer, on the host) |
| Android, native | `cd android && tools/build.sh` | same |
| Android, Termux | [termux/docs/building.md](termux/docs/building.md) | [termux/docs/](termux/docs/) |
| Web | [web/README.md](web/README.md#quick-start) | `web/tools/test/smoke.py` |
| Docker | `docker build --build-arg ANKI_PY_VERSION=… desktop` ([desktop/README.md](desktop/README.md)) | `desktop/test/run.sh` |

The Anki version for every variant is set in
[`shared/versions.env`](shared/versions.env). GitHub Actions build the apps
on a `v*` tag and attach them to the release; the Docker image is built,
tested and pushed to `ghcr.io/krmanik/kioku-desktop` on a release.

## Credits

Kioku stands on [Anki](https://apps.ankiweb.net), [Qt](https://www.qt.io) and
[PyQt](https://riverbankcomputing.com/software/pyqt/),
[BeeWare's Python builds](https://github.com/beeware/Python-Apple-support) and
[rubicon-objc](https://github.com/beeware/rubicon-objc),
[Termux](https://termux.dev) and its packages,
[Termux:X11](https://github.com/termux/termux-x11),
[JWM](https://joewing.net/projects/jwm/),
[Emscripten](https://emscripten.org), and LinuxServer.io's
[Selkies](https://github.com/linuxserver/docker-baseimage-selkies) image.
Anki is AGPL-3.0; see [termux/docs/distribution.md](termux/docs/distribution.md)
for the other licenses.

## License

Kioku is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE),
the same license as Anki. Forks and redistributed builds must keep that license
and offer their source.

"Anki" is a trademark of Ankitects. Kioku is an independent project, not
affiliated with or endorsed by Ankitects.
