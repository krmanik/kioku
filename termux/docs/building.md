# Building Kioku

## Releases from GitHub Actions

`.github/workflows/release.yml` builds the runtime and the APK on GitHub's runners:

* **Push a tag** such as `v0.2.0` (`git tag v0.2.0 && git push origin v0.2.0`): the workflow
  builds `Kioku-0.2.0-arm64.apk` and attaches it, with `SHA256SUMS.txt`, to the GitHub release
  of that tag.
* **Run it by hand** (Actions → Release APK → Run workflow): the APK is kept as a workflow
  artifact; give a tag to publish it to that release as well.

The version name comes from the tag and the version code from the run number, so every build
can update the previous one.

### Signing

Android only updates an app with an APK signed by the same key, so sign every release with one
key of your own. Create it once and keep it (and its passwords) safe:

```sh
keytool -genkeypair -v -keystore kioku.jks -alias kioku -keyalg RSA -keysize 4096 -validity 10000
base64 -i kioku.jks | tr -d '\n'     # macOS; on Linux: base64 -w0 kioku.jks
```

Then add these repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `KIOKU_KEYSTORE_BASE64` | the base64 output above |
| `KIOKU_KEYSTORE_PASSWORD` | the keystore password |
| `KIOKU_KEY_ALIAS` | `kioku` (the alias above) |
| `KIOKU_KEY_PASSWORD` | the key password, if different from the keystore password |

Without them the workflow signs with a throwaway debug key and warns.

## Local build

Requirements: Android SDK, NDK `30.0.14904198` (see `gradle.properties`), JDK 21, Python 3.

All commands run in the `termux/` folder of the repository.

```sh
cd termux
git submodule update --init third_party/termux-x11
git -C third_party/termux-x11 submodule update --init --depth 1
# macOS only, see the end of "Local changes to third-party code"
(cd third_party/termux-x11/lorie/src/main/cpp && for p in pixman:pixman xkbcomp:xkbcomp \
    libxkbfile:xkbfile libx11:x11 libxtrans:Xtrans xserver:xserver libepoxy:libepoxy; do
    patch -p1 -N -d "${p%%:*}" -i "$PWD/patches/${p##*:}.patch" </dev/null; done)

# Runtime: Termux packages (+ the anki release of krmanik/termux-packages), cross-compiled
# PyQt6.sip and PyQt6.QtPdf, pure-Python deps (tools/python-requirements.txt), pruned and zipped.
tools/build_bootstrap.sh          # Linux: SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The packages that are not in the Termux repositories yet (anki, python-markupsafe,
python-orjson) come from the release `anki-<ANKI_TAG>` of
[krmanik/termux-packages](https://github.com/krmanik/termux-packages/releases), with `ANKI_TAG`
from `shared/versions.env`: `tools/fetch_anki_debs.py` downloads them to `build/anki-debs/` and
checks their SHA-256. They take precedence over the repositories' packages, and .debs you put in
`local-debs/` (not committed) take precedence over both.

## Building the anki package

Releases on krmanik/termux-packages named `anki-<version>` hold the `anki` .deb, and the runtime
build downloads the one for `ANKI_TAG` (see above).

The package keeps Termux's default package name (paths under `/data/data/com.termux`), which
`tools/build_rootfs.py` retargets, so do not set `TERMUX_APP__PACKAGE_NAME` and do not use
`tools/build-termux-packages.sh` for it.

### With GitHub Actions

The `anki` workflow on krmanik/termux-packages (`.github/workflows/anki.yml`, on `master`) builds
it: Actions → anki → Run workflow, with the Anki version (empty: the version in the recipe). It
takes the recipes from the `anki` branch and lays them over the current upstream master, so the
branch does not need rebasing. The release is created, marked latest, with the .debs and
`SHA256SUMS.txt`; untick "Publish the release" to only keep them as a workflow artifact.

Anki's build output (Rust targets, node_modules, about 1.7 GB compressed) and the downloaded
dependencies stay in the Actions cache (`ANKI_BUILD_CACHE` in the recipe), and python-markupsafe
and python-orjson are reused while their recipes are unchanged. GitHub drops caches unused for 7
days, so a weekly scheduled run of the same workflow restores them to keep them. Untick "Use the
build cache" to build from scratch.

Kioku's "Anki update" workflow bumps `ANKI_TAG` and `versionName`, and its pull request says
whether the release exists yet.

### By hand in a Codespace

1. In `~/termux-packages` (branch `anki`), bump `TERMUX_PKG_VERSION` in
   `x11-packages/anki/build.sh` and rebase onto the current upstream master:

   ```sh
   git fetch upstream master && git rebase upstream/master
   git push --force-with-lease origin anki
   ```

   `-i` below downloads each dependency at the exact version its recipe names, and the Termux
   repositories only keep the newest one. A branch a few days behind builds the outdated
   dependencies from source instead (14 of them, harfbuzz among them, after 4 days), which takes
   longer and links anki against libraries older than the phone's.

2. Create a 4-core codespace (`standardLinux32gb`: 4 cores like GitHub's runners, 16 GB RAM,
   $0.36/hour; it needs the `codespace` scope, `gh auth refresh -h github.com -s codespace`):

   ```sh
   gh codespace create -R krmanik/termux-packages -b anki -m standardLinux32gb --idle-timeout 120m
   gh codespace ssh -c <name>
   ```

3. Its root disk has 12 GB free, too little for the build, while `/tmp` is a separate disk with
   about 110 GB. Move Docker there. `/tmp` has a default ACL without execute for others, which
   the image layers would inherit, so the container's `builder` user could not run anything
   (`exec /bin/bash failed: Permission denied`); strip it on the new directories:

   ```sh
   sudo apt-get install -y acl
   sudo pkill dockerd; sleep 3; sudo pkill containerd; sleep 2
   for d in docker containerd; do
       sudo mkdir /tmp/$d && sudo setfacl -bk /tmp/$d && sudo chmod 711 /tmp/$d
       sudo mount --bind /tmp/$d /var/lib/$d
   done
   sudo sh -c 'nohup containerd --config /etc/containerd/config.toml >/tmp/containerd.log 2>&1 &'
   sudo sh -c 'nohup dockerd --containerd /run/containerd/containerd.sock --dns 168.63.129.16 >/tmp/dockerd.log 2>&1 &'
   ```

4. Build, in the background so a dropped connection does not stop it:

   ```sh
   cd /workspaces/termux-packages
   nohup ./scripts/run-docker.sh ./build-package.sh -i -a aarch64 anki > /tmp/anki-build.log 2>&1 &
   ```

5. Check `output/anki_<version>_aarch64.deb` (`dpkg-deb -f … Depends`, `dpkg-deb -c`: paths under
   `./data/data/com.termux`), copy it out and publish it:

   ```sh
   gh codespace cp -e -c <name> 'remote:/workspaces/termux-packages/output/*.deb' .
   gh release create anki-<version> -R krmanik/termux-packages --target <full commit sha> \
       --latest anki_<version>_aarch64.deb python-markupsafe_*_aarch64.deb python-orjson_*_aarch64.deb
   gh codespace stop -c <name>
   ```

   python-markupsafe and python-orjson are rebuilt as well; attach them too, since the release
   is where the runtime build finds them.

### Build times

Measured on 2026-10-23 for 26.09.3, all on 4 cores:

| Step | Codespace | Actions, no cache | Actions, cached |
|---|---|---|---|
| Restore the cache | | | 34 s |
| Pull the builder image, create the container | 4 min 50 s | 2 min 2 s | 1 min 29 s |
| Download the dependencies | 3 min 35 s | 1 min 36 s | 29 s |
| python-markupsafe (mostly building the host Python) | 6 min 53 s | 2 min 4 s | reused |
| python-orjson | 36 s | 29 s | reused |
| anki: `ninja wheels`, rsbridge for Android, packaging | 13 min 8 s | 9 min 26 s | 4 min 35 s |
| Save the cache | | 18 s | 27 s |
| **Whole run** | **29 min 3 s** | **16 min 9 s** | **7 min 44 s** |

With the cache, Anki's own crates are still compiled (with LTO, about 2 min 15 s for rsbridge);
a new Anki version changes them anyway.

## Application id and the runtime

Termux binaries hardcode `/data/data/<package>/files/usr`, so the runtime has to be made for the
app's id (`ankideskApplicationId` in `gradle.properties`). Rebuilding every Termux package for a
new id takes a day of compiling, so `tools/build_rootfs.py` retargets the official packages in
place instead, which only works when each path keeps its length. `io.ankidesk` is one character
longer than `com.termux`, so the rootfs directory loses one: `file/` instead of `files/`
(`ankideskRootfsDir`).

| | path | length |
|---|---|---|
| Termux | `/data/data/com.termux/files/usr` | 31 |
| Kioku | `/data/data/io.ankidesk/file/usr` | 31 |

* The app gets the directory as `BuildConfig.ROOTFS_DIR`; the bootstrap's `MANIFEST.txt` records
  the package and rootfs it was made for, and the app refuses a runtime made for another.
* termux-exec has the bare `/data/data/com.termux` as a default, which cannot be rewritten in
  place. It prefers `TERMUX_APP__DATA_DIR`, `TERMUX_APP__LEGACY_DATA_DIR`, `TERMUX__ROOTFS` and
  `TERMUX__PREFIX` from the environment, which `Prefix.environment()` sets.
* Apps installed from the Software page are rewritten the same way when they are unpacked
  (`ankidesk_pkg.py`).

Packages compiled for the id (`tools/build-termux-packages.sh ~/termux-packages` on x86_64 Linux,
then the .debs in `local-debs/`) need no rewriting: set `ankideskRootfsDir=files` and run
`SOURCE_PACKAGE=io.ankidesk tools/build_bootstrap.sh io.ankidesk files`.

Termux limits the package name to 33 characters (21 recommended) because of Unix socket
(108) and shebang (127) path limits.

## Size

| | |
|---|---|
| Typical Termux install used to build/run Anki | ~3.4 GB |
| Anki runtime closure (dpkg) | ~1.1 GB |
| Bundled prefix after pruning | ~625 MB |
| `bootstrap-aarch64.zip` in the APK | ~230 MB |

Pruned: headers, static libs, docs, translations other than English for WebEngine, Qt tools,
perl, mesa + LLVM (Qt and Chromium run without OpenGL), gstreamer.

## Known gaps in the Termux packages

* `pyqt6` installs `PyQt6-sip` with pip in its postinst (compiling it on the phone);
  `tools/build_pyqt6_sip.sh` cross-compiles it instead. `python-pyqt6-sip` from
  krmanik/termux-packages would replace this once it is in the repositories.
* `pyqt6` is built without the QtQuick bindings and Qt's OpenGL classes. Anki imports both but
  only uses them for GPU selection; `launch_anki.py` provides stand-ins.
* `pyqt6` is built without the QtPdf and QtPdfWidgets bindings (it doesn't depend on
  `qt6-qtwebengine`, which has `libQt6Pdf`), so add-ons that import `PyQt6.QtPdf` fail to load.
  `tools/build_pyqt6_pdf.sh` generates them with sip against the prefix's PyQt6 bindings and
  cross-compiles them.
* `pyqt6` is built without `PyQt_Accessibility`, which drops `QWidget.setAccessibleName` and
  similar accessors that add-ons call; `launch_anki.py` adds ones that keep the values.

## Local changes to third-party code

`third_party/termux-x11` is the `kioku` branch of
[krmanik/termux-x11](https://github.com/krmanik/termux-x11/tree/kioku), a fork of
termux/termux-x11 with these commits on top:

* `third_party/termux-x11/lorie/version.gradle`: NDK version can be overridden with the
  `termuxX11NdkVersion` Gradle property.
* `third_party/termux-x11/lorie/src/main/cpp/lorie/renderer.cpp`: core cursors (≤ 32 px) are
  drawn three times larger.
* `third_party/termux-x11/lorie/src/main/cpp/recipes/xkbcomp.cmake`: a `case-compat` include
  dir with bionic's `xlocale.h`, which on case-insensitive filesystems (macOS) otherwise
  resolves to libX11's `X11/Xlocale.h`.

To move to a newer termux-x11:

```sh
cd third_party/termux-x11
git fetch upstream && git rebase upstream/master    # remotes: origin = fork, upstream = termux
git push --force-with-lease origin kioku
cd ../.. && git add third_party/termux-x11  # in termux/ && git commit -m "Update termux-x11"
```

On macOS: termux-x11 applies its own submodule patches at CMake configure time with
`patch -R --dry-run || patch …`. Apple's `/usr/bin/patch` exits 0 on a failed reverse dry run,
so nothing gets patched (`'GL/gl.h' file not found`); apply them by hand as in
[Local build](#local-build).
