# Distribution and licenses

## Where Kioku can be published

* **GitHub Releases** (what this repository does, see [building.md](building.md#releases-from-github-actions)):
  the APK is attached to each tagged release and installed by hand.
* **Google Play**: possible for Anki itself: everything ships in the app bundle; the runtime goes
  into an install-time asset pack (≤ 1.5 GB per pack). Targets API 36. Executing bundled binaries
  relies on the system linker, as the Play build of Termux does. The Software page downloads
  executable code, which Play's policy forbids outside Play; a Play build would have to ship the
  optional apps as on-demand asset packs or leave that page out.
* **F-Droid**: would have to build all Termux packages, including Qt WebEngine, from source.
  GitHub Releases or a self-hosted F-Droid repo are simpler.

## Licenses

Kioku itself is AGPL-3.0-or-later ([LICENSE](../../LICENSE)), as is Anki. termux-x11 and the Termux packages are GPL-3.0 and others. Distributing the APK
means offering the corresponding source: this repository, termux-x11 (`third_party/`, the
`kioku` branch of krmanik/termux-x11), and the Termux package recipes (termux/termux-packages
and the `anki` branch of krmanik/termux-packages).

"Anki" is a trademark of Ankitects, hence the app's own name, Kioku (記憶, Japanese for
"memory"). Kioku is not affiliated with or endorsed by Ankitects.
