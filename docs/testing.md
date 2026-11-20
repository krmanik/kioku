# Testing the native variants

## How

Both native variants have a development mode (`KIOKU_DEV=1`, set by the run
scripts) with a command channel into the running app
(`shared/python/kioku/devtools.py`):

- `ios/tools/run_device.sh` builds, installs and launches on a connected
  iPhone (`KIOKU_TEAM=<team id>` for signing) and prints the app's log.
- `ios/tools/devcmd.sh [--shot] 'python'` runs Python inside the app (with
  `mw`, `aqt`, `shot()`, `widgets()`) and prints its output; `--shot` also
  fetches a screenshot (web views included).
- `ios/tools/sweep.sh` opens every main window and reports widgets that run
  off the screen.

Code run through `devcmd.sh` runs on the main thread: anything that waits for
the main thread (AnkiConnect requests, for example) has to run in a
`threading.Thread`. A command that opens a modal dialog (a prompt, a message
box) and then waits blocks the channel until the dialog closes; open modal
dialogs with `QTimer.singleShot(0, …)` and return, then handle them in the
next command. On iOS, `devicectl` sometimes reports a failed copy although the
command arrived (the app had already picked the file up); `devcmd.sh` waits
for the output anyway.

Test collections: real desktop profiles exported with Anki 26.8.1's own
library (`export_collection_package`) from an APFS clone (`cp -c`) of the
profile folder, so the desktop data is never opened, pushed with
`xcrun devicectl device copy to … Documents/Import/` and imported with
`aqt.import_export.importing.ColpkgImporter._import(mw, path)`.

## Automated tests

One command runs everything that needs no hands, and can run unattended
(cron, launchd, a CI machine with a simulator or emulator):

```sh
shared/tools/test_all.sh                  # host tests + every target found
shared/tools/test_all.sh android ios-sim  # only these
KIOKU_BUILD=1 shared/tools/test_all.sh    # build and install first
```

- `host`: `shared/tests/run.sh`, Kioku's Python code against desktop Anki
  of `ANKI_TAG` with a patched rsbridge. It also runs the installed Anki's
  request interceptor against the Qt WebEngine stand-in and checks that every
  `QWebEngine*` name aqt uses exists there, so an Anki update that needs more
  of Qt WebEngine fails here before it reaches a phone.
- `android` (the emulator or phone adb sees, `ANDROID_SERIAL`), `ios-sim`
  (a booted simulator with Kioku, `KIOKU_SIM`), `ios` (a connected iPhone,
  `KIOKU_DEVICE`): `shared/tools/apptest.py` relaunches the development
  build, answers a fresh install's language and profile questions, then runs
  [shared/tests/app/suite.py](../shared/tests/app/suite.py) inside the app
  and the crash sweep (`ios/tools/smoke.py`, every window once).

The in-app suite works in a deck "Kioku Test" in the open profile and
removes it at the end:

| Test | What it does |
| --- | --- |
| version, profile | Anki is `ANKI_TAG`; a profile and collection are open |
| add | adds Basic and Cloze notes, one with a picture |
| add-window | Add window: the note's text reaches the editor page, Add saves it to the deck, the editor clears; `activeWindow()` is Add |
| editor-formatting | Add window: on a selection in a field, bold, italic, underline, superscript, subscript (on and off again), text colour, highlight, remove formatting, MathJax inline, cloze (Cloze note); underline at the caret, then a typed letter is underlined |
| editor-caret | Add window: a field that gets the focus back without a tap (after the next field had it) keeps its caret, and a backward selection |
| deck-list | the deck list shows the deck |
| browse | search, row count, the editor page shows the selected note, Add over Browse is the active window |
| study, review, undo | overview, the picture card's question with its picture drawn, the answer, Good (review logged, next card), undo |
| gamepad | the default controls through kioku.gamepad into Anki's shortcuts: Down highlights the test deck, A opens it, A studies, B on the question does nothing, A shows the answer, B answers Again (review logged), L1 undoes it, View and B go back |
| gamepad-native | Android: real `KeyEvent`s (source gamepad: A, Start, d-pad) and a joystick `MotionEvent` (stick, right stick, hat, trigger) through `KiokuActivity` reach Python; a keyboard's arrow is not taken. iOS: Apple's `GCVirtualController` connects and disconnects as a controller Kioku watches; A pressed through Kioku's handler (iOS 17+; older: a snapshot's A) |
| media-server | the media server hands out the picture |
| statistics, deck-options | the pages load through the API (graphs drawn, inputs present) |
| export-apkg, export-csv, export-window | packages and notes exported; the Export window opens |
| import-apkg, import-csv, import-window | the test notes removed and imported back with the picture; CSV import; the import screen loads |
| check-database, check-media | both pass, the picture isn't missing |
| sync-server | the local sync server starts on a free port, answers `/health`, stops |
| python-packages, programs | numpy, Pillow, cryptography, PyMuPDF, QtPdf … import; the bundled programs run |
| microphone | iOS: Info.plist has `NSMicrophoneUsageDescription` (issue #19); with the permission granted (`apptest.py ios-sim` grants it), one second recorded through `AVAudioRecorder` as an add-on does, then card audio's session restored. Never asks: on an iPhone that wasn't asked yet it checks the key only |
| https | ankiweb.net answers with a verified certificate (`--no-network` skips) |

`python3 -I shared/tools/apptest.py android --only browse,review` runs
some tests (with what they need); `--list` names them. Reports:
`build/test-reports/<target>-<time>.md` and `.xml` (JUnit). Exit status 1
when something failed.

## Results: iOS (iPhone 15 Pro Max, iOS 26, Anki 26.8.1)

Collections: 41, 602, 61,199 and 258,430 cards (27k media files) imported,
card and review counts identical to the desktop.

| Area | Result |
| --- | --- |
| Start-up, profiles, switching profiles | works |
| Deck list (258k cards) | works; fits the screen |
| Reviewing: question, answer, answer buttons, intervals, revlog written | works |
| Card audio (mp3) | works, including interrupting and the next card |
| Card audio: Ogg Vorbis, Ogg Opus | works (iOS 27.0.1): AVAudioPlayer can't play Ogg, so these play in a hidden web view; stopping mid-file and the next file work |
| `{{tts}}` text-to-speech | works: AVSpeechSynthesizer, 193 voices (Apple_Samantha …); stop mid-sentence works |
| Statistics (new stats page, charts, calendar) | works |
| Statistics: Save PDF | works: 4-page A4 PDF in Documents/Exports |
| Browse | works; sidebar behind a title bar button in portrait |
| Add, editor | works |
| Image occlusion: mask editor with an image | works (masks need touch testing) |
| Image occlusion / import / attachments: choosing a file | fixed (document picker in copy mode); needs a hand test |
| Import .colpkg | works |
| Export | writes to Documents/Exports |
| Preferences, Note Types, Deck Options, Filtered Deck, Study Deck, Add-ons, About | open, fit the screen, close with ‹ Back |
| HTTPS (add-on downloads) | works after the truststore fix |
| AnkiWeb sync | works (physical-device round below): login, full download, media sync, two-way changes, conflict choice |

Popups (shared code, after the Android round): the AnkiWeb login is a card
above the keyboard (iOS reports the keyboard in points, as assumed);
closing it and opening another window with the keyboard up works.

### Add-ons

Installed from AnkiWeb inside the app; all 15 load without errors.

| Add-on | Code | Result |
| --- | --- | --- |
| AnkiConnect | 2055492159 | works: HTTP API on 127.0.0.1:8765 answers (version, deckNames, findCards) |
| Review Heatmap | 1771074083 | works: heatmap on the deck list (slightly wider than a phone screen) |
| Anki Simulator | 817108664 | opens; rendering to check |
| AnKing Note Types Easy Customization | 952691989 | loads, menu works; shows a tutorial at start-up |
| Advanced Browser | 874215009 | loads; to check |
| Fill the blanks | 1933645497 | loads; to check |
| Colorful Tags / Hierarchical Tags | 594329229 | loads; to check |
| Customize Keyboard Shortcuts | 24411424 | loads |
| Edit Field During Review Cloze | 385888438 | loads; to check |
| Speed Focus Mode | 1046608507 | loads |
| True Retention | 613684242 | loads; to check |
| HyperTTS | 111623432 | loads; its configuration window did not appear: to check |
| AnkiWebView Inspector | 31746032 | loads; needs Qt WebEngine dev tools, expected not to work (use Safari's Web Inspector instead: web views are inspectable) |
| Color Confirmation | 1084228676 | works (answer confirmation popup) |
| Japanese Support | 3918629684 | loads; Kanji Stats did not open, and readings use MeCab as a subprocess, which iOS forbids: to check |

AnkiWeb returned 404 for 516643804, 2091361802 and 1572969437 (codes no
longer published).

## Results: Android (emulator, Android 17 arm64, 16 KB pages, Anki 26.8.1)

Android has the same tools: `android/tools/run_device.sh` (build, install,
launch in dev mode, print the log; `KIOKU_NO_BUILD=1` reinstalls the last
build), `devcmd.sh [--shot] 'python'` (screenshots with `adb screencap`) and
`sweep.sh`. Collections are pushed with
`adb push … /sdcard/Android/data/io.ankidesk.kioku/files/Import/`.

Emulator: start it with `emulator -avd Medium_Phone -gpu swiftshader_indirect
-feature GLESDynamicVersion`. With `-gpu host` on a Mac it offers only OpenGL
ES 3.0, and WebView aborts the app on pages with embedded video (see
docs/fixes.md).

Collections: the same 41, 602, 61,199 and 258,430-card profiles imported,
counts identical to the desktop.

| Area | Result |
| --- | --- |
| Start-up, profiles, switching profiles | works |
| Menu bar | works (drawn as a widget) |
| Back key | closes the top window; on the main window moves the app to the background |
| Background and resume | works; no error dialog |
| Deck list (258k cards) | works |
| Reviewing: question, answer, answer buttons, revlog written | works |
| Card audio: mp3, wav, ogg (Vorbis), opus | works, Anki's queue gets "done" for each |
| Statistics (new stats page, charts, calendar) | works |
| Statistics: Save PDF | works (5-page PDF in Exports/) |
| Browse, sidebar, notes with embedded YouTube video | works (emulator: needs the ES 3.1 setting above) |
| Add, editor | works (note added through the Add window) |
| Import .colpkg | works |
| Export (.apkg) | writes to Exports/ in the app's external files folder |
| About, Browse, Add, Statistics, Preferences, Note Types, Deck Options, Filtered Deck, Study Deck, Empty Cards, Export, Add-ons | open full screen, nothing wider than the screen (`sweep.sh`, also after the small-dialog change) |
| HTTPS (add-on downloads) | works after the CA bundle fix |
| Image occlusion / file picking | system picker opens; needs a hand test |
| AnkiWeb sync (User 4) | works: login, full sync (download, 39,754 cards), media sync; still logged in after a force-stop and restart |
| Popups: AnkiWeb login, rename prompt, message boxes | bordered card sized to its content; above the keyboard while typing |
| Top bar height over 5 cold starts | 34 px each time (the retry was needed in 2 of 5) |
| AnkiWeb login: OK tapped with the keyboard up, error box follows | works (5 of 5); crashed before the Qt plugin patch |
| Samsung M30s (Android 11, real device) | start-up, `sweep.sh` (all windows full screen), login card above the keyboard, OK with the keyboard up |

### Add-ons (Android)

All 15 installed from AnkiWeb inside the app and load without errors.

| Add-on | Result |
| --- | --- |
| AnkiConnect | works: version 6, deckNames (252 decks) |
| Review Heatmap | works: heatmap drawn on the deck list (366 day cells) |
| Anki Simulator | opens |
| AnKing Note Types Easy Customization | loads, AnKing menu; shows a tutorial at start-up (add-on loading waits until it is closed, as on the desktop) |
| Advanced Browser | loads (its modules are active in Browse) |
| Fill the blanks | loads |
| Colorful Tags / Hierarchical Tags | loads; sidebar works |
| Customize Keyboard Shortcuts | loads (logs a deprecation warning for `tr(TR.…)`) |
| Edit Field During Review Cloze | works (its EFDRC script is in the card page) |
| Speed Focus Mode | loads |
| True Retention | works: its rows in the legacy statistics window (Shift+Stats) |
| HyperTTS | works: configuration window opens; editor buttons shown |
| AnkiWebView Inspector | loads; needs Qt WebEngine dev tools (use chrome://inspect: web views are debuggable) |
| Color Confirmation | works (popup after answering) |
| Japanese Support | works: Kanji Stats opens with statistics; MeCab readings to check |

## Results: physical devices, user flows (October 22, 2026)

iPhone 15 Pro Max (iOS 26) and Samsung Galaxy M30s (Android 11, 3.6 GB RAM),
both on the builds installed that day (no rebuild). On the Samsung every step
was done with real taps, swipes and the on-screen keyboard (`adb shell input`),
the way a user would; on the iPhone, where input can't be injected, with
`devcmd.sh` clicking the same buttons and links (Qt events, JavaScript
`click()` in the web views) and checking screenshots. Collections: the
258,430-card profile (27k media files) and an AnkiWeb account with 39,754
cards and 13,677 media files.

✅ works, ⚠️ works with a problem, ❌ doesn't work.

### Getting started

| Area | iOS | Android |
| --- | --- | --- |
| Cold start to the deck list (258k cards, one add-on) | ✅ ~6 s | ✅ ~17 s |
| Import a .colpkg with the system file picker (290 MB, 27k media) | not driven (picker can't be scripted) | ✅ about 15 min on the M30s; "replace collection" box, progress, all cards and media |
| Cancel the file picker | – | ✅ |
| Profiles: create, switch (File › Switch Profile), open | ✅ | ✅ |
| File › Exit | ✅ app closes | ✅ app closes, no crash; relaunch from the launcher works |
| Last profile and AnkiWeb login kept after a restart | ✅ | ✅ |

### Studying

| Area | iOS | Android |
| --- | --- | --- |
| Deck list: open a deck, overview, Study Now | ✅ | ✅ real taps |
| Card JavaScript (tap-to-order characters, hint button) | ✅ | ✅ real taps |
| Show Answer, answer buttons with intervals, revlog written | ✅ | ✅ |
| Undo after answering | ✅ | not repeated |
| Flag, mark, bury, suspend (and undo) | ✅ | not repeated |
| Card info (forgetting curve) | ✅ | not repeated |
| Edit current card, change a field, saved | ✅ | not repeated (editing tested in Add and Browse) |
| Card audio (mp3), replay button | ✅ AVFoundation | ✅ MediaPlayer |
| `{{tts}}` text-to-speech | ✅ fixed later that day: AVSpeechSynthesizer (see below) | ✅ fixed later that day: TextToSpeech (see below) |
| Links in cards (`<a href>`) | – | ✅ open the system browser chooser |
| Landscape | not driven | ✅ layout adapts; drag to scroll works |
| Back key while reviewing | – | ⚠️ moves the app to the background (AnkiDroid users expect the deck list) |
| Status and navigation bars after another app's popup (browser chooser) | – | ✅ fixed later that day (see below); before: both bars stayed hidden until the app restarted |

### Adding and editing

| Area | iOS | Android |
| --- | --- | --- |
| Add: type into fields with the keyboard, Add | ✅ | ✅ the window shrinks above the keyboard |
| Note type and deck choosers, typing in the filter | ✅ | ✅ |
| History button label | ✅ "History ▾" | ⚠️ "History ▯" (the ▾ glyph is missing from the font) |
| Image occlusion: pick an image, draw a mask by touch, Add | not driven (picker) | ✅ |
| Image picker filtered to images | – | ⚠️ shows every file type |
| Card types editor (Cards…) | ⚠️ opens, cramped in portrait | ⚠️ opens, cramped in portrait (labels cut: "Fror", "Bac") |

### Browse

| Area | iOS | Android |
| --- | --- | --- |
| Open, search, select a row, editor below the table | ✅ | ✅ |
| Searching with the keyboard's Enter key | ✅ | ✅ fixed later that day (see below); before: the keyboard showed "Next" and moved the focus instead of searching |
| Sidebar button, sidebar search | ⚠️ works; the sidebar squeezes the editor (Back field under Tags) | ✅ |
| Preview, Change Deck, Delete notes | ✅ | not repeated |
| Window title | ⚠️ long titles are cut at both ends ("rowse (24 of 24 cards selectec") | ✅ |

### Decks, statistics, tools

| Area | iOS | Android |
| --- | --- | --- |
| Create Deck prompt (card above the keyboard) | ✅ | ✅ with the Enter-key fix; without it the keyboard's Next only moves to the buttons |
| Deck gear menu: rename, options, delete | ✅ | not repeated |
| Deck options: change a limit, Save | ✅ | opens (`sweep.sh`); saving not repeated |
| Filtered deck: build, study, delete | ✅ | ✅ |
| Statistics page | ✅ | ✅ |
| Statistics: Save PDF | ✅ fixed later that day: A4 PDF in Documents/Exports (see below) | ⚠️ PDF written to `Exports/`, but no message says so |
| Export (.colpkg) | ✅ Documents/Exports, visible in Files | ⚠️ written to `Android/data/io.ankidesk.kioku/files/Exports`, which Android 11+ hides from most file managers; there is no share option |
| Create Backup | ✅ | ✅ |
| Check Database, Check Media, Empty Cards | ✅ | ✅ (identical results on both) |
| Preferences: switch to Light and back | ✅ | ✅ |
| Every main window full screen, nothing wider than the screen (`sweep.sh`) | ✅ 12 windows | ✅ 12 windows |
| Review Heatmap on the deck list | ⚠️ slightly wider than the screen | ⚠️ slightly wider than the screen |

### Add-ons

| Area | iOS | Android |
| --- | --- | --- |
| Tools › Add-ons › Get Add-ons, code 1771074083 (Review Heatmap) | ✅ downloaded and installed | ✅ |
| Add-on active after restarting the app | ✅ | ✅ |

### AnkiWeb sync (both phones on the same account)

Tested in a new, empty profile on each phone so the account's data was never
uploaded over.

| Step | iOS | Android |
| --- | --- | --- |
| Login card, typing email and password, OK | ✅ | ✅ |
| Empty profile: "Download from AnkiWeb?", full download (39,754 cards) | ✅ | ✅ |
| Media sync (13,677 files, about 15 files/s) | ✅ same files on both | ✅ |
| Sync while media is still syncing | shows the media sync log (as on the desktop) | same |
| Note added on Android appears on iOS after syncing both | ✅ | ✅ |
| Field edited on iOS appears on Android | ✅ | ✅ |
| Same note edited on both before syncing | ✅ the later edit wins on both, no prompt | ✅ |
| Note deleted on Android disappears on iOS | ✅ | ✅ |
| Schema change (new field) → conflict box: Upload / Download / Cancel | ⚠️ box fills the screen with a large empty gap | ✅ card with stacked buttons |
| Choosing Download resolves the conflict | ✅ | ✅ |
| Auto sync when opening and closing a profile | ✅ | ✅ |

Check Database marks the collection for a full sync (as on the desktop), so
the next sync asks Upload/Download again.

### Open problems found in this round

- **Android: keyboard Enter = "Next".** Qt reports `EnterKeyNext` for
  single-line fields, so Browse's search, prompts and the login can't be
  submitted from the keyboard. Fixed in `shared/python/kioku/windows.py`
  (`EnterKeyFilter`); verified in the build installed later that day.
- **Android: system bars disappear** after a popup from another app (the
  "Open with" browser chooser). Qt 6.11's
  `QtWindowInsetsController.isFullScreen()` (API 30+) treats "status bar not
  visible" as full screen when the window regains focus, and
  `restoreFullScreenVisibility()` then hides the bars for good. Fixed:
  `KiokuActivity.onWindowFocusChanged` shows the bars instead.
- **Android: exports are hard to reach** on Android 11+ (`Android/data`).
  A share sheet or a document provider would fix it.
- Fixed later that day: iOS Save PDF, `{{tts}}` on both, iOS Ogg audio (see below).
- Cosmetic: Browse title cut on iOS, "History ▯" glyph on Android, cramped
  card types editor, iOS conflict box layout, Review Heatmap a little too wide.

### Fixes tested later the same day

New builds with the fixes on both phones (installed over the old ones, data
kept): iPhone 15 Pro Max (now iOS 27.0.1) and Samsung M30s.

| Fix | iOS | Android |
| --- | --- | --- |
| Ogg Vorbis and Ogg Opus card audio | ✅ hidden web view fallback; through Anki's queue, stop mid-file, mp3 unchanged | already worked (MediaPlayer) |
| Browse search from the keyboard | – | ✅ keyboard shows ✓ instead of Next; tapping it runs the search (301 → 602 cards) |
| `{{tts}}` | ✅ 193 voices, `en_US` → Apple_Samantha; stop mid-sentence | ✅ Samsung engine's 4 voices (en_US, en_GB, en_IN, hi_IN); a sentence spoken and reported done |
| Statistics: Save PDF | ✅ 4 A4 pages | (already worked) |
| System bars after the "Open with" chooser | – | ✅ both bars back after closing the chooser |

Samsung's TTS engine reports locales as `eng` (no country); the language is
taken from its voice names (`en-US-SMTf00`).

## Sync server and AnkiDroid's media (2026-10-22)

Guide: [sync-server.md](manual/src/features/sync-server.md). Fixes: [fixes.md](fixes.md#sync-server-and-ankidroids-folder-preferences--advanced).

### Host tests (`shared/tests/run.sh`, macOS, Anki 26.8.1 + patched rsbridge)

48 tests, all passing (three runs in a row for the server tests):

- Server: start, stop, restart on the same port, 25 start/stop cycles without
  leaking threads, port already in use, bad settings, Tailscale not
  connected, "All networks", the password never left in the environment.
- Syncing through it with real Anki clients: full upload/download, changes
  both ways, media both ways, wrong password and unknown user refused, a
  restart keeps data and logins, a new password needs a new login, Delete
  server data means a full upload, stopping during a 300-file media upload
  (stop returns, client doesn't hang, media complete after a restart), three
  clients syncing at once (Anki's "only one copy can sync" error for some,
  nothing lost after syncing again).
- AnkiDroid's folder: media folder override (Python side and backend, kept
  after a reopen, other collections unaffected, AnkiDroid's
  `collection.media.db` untouched), both "apps" open with media sync off and
  nothing uploaded to the server, a second process holding the collection
  (locked → message, fallback to the profile's own collection, setting turned
  off and saved), closing for the background and reopening.
- The Advanced tab (offscreen Qt): off by default, declined warning, first
  enable makes a password, settings survive a new window, port change
  restarts, bad values refused, port in use shown in red, Use for this
  profile (and declining to leave AnkiWeb, and a wrong password), Delete
  server data; the AnkiDroid group's choices, checks and what it saves on
  close.

A test helper bug found on the way: notes made in the same millisecond in
different collections get the same id, which looked like lost changes.

### Devices

Android emulator (API 37, arm64) with AnkiDroid 2.25.3 (GitHub "full" build,
`/storage/emulated/0/AnkiDroid`); iPhone 15 Pro Max (iOS 27.0.1).

| Test | Android | iPhone |
| --- | --- | --- |
| Advanced tab fits the screen | ✅ | ✅ (dark mode) |
| Turning the server on (tap, warning, Yes) | ✅ | ✅ |
| Server starts with the app, before the profile's sync check | ✅ (after a fix) | ✅ |
| Foreground service, notification, Stop action | ✅ type `specialUse`; notification shown again after allowing notifications (after a fix); Stop ends server and service, setting kept | – |
| Desktop Anki (Mac, through `adb forward`) uploads 20 notes with media; a Kioku profile downloads them through Anki's own sync UI | ✅ | – |
| Kioku profile adds a note with media and syncs; the desktop gets both | ✅ | – |
| …while Kioku was in the background for 2.5 minutes | ✅ (process kept as a foreground service) | – |
| Use for this profile, upload, a second profile downloads | ✅ | ✅ |
| Server after 60 s in the background (Settings app in front) | – | ✅ still answering |
| AnkiDroid logs in to `http://127.0.0.1:8080/` and syncs | ✅ | – |
| AnkiDroid's media: Kioku's note with an image goes into AnkiDroid's folder, AnkiDroid gets the note; AnkiDroid's note reaches Kioku; no media uploaded to the server | ✅ | – |
| All files access check, AnkiDroid version, folder checks | ✅ | – |

Not done yet: Samsung M30s (Android 11's storage), Tailscale and "All
networks" from another machine, iOS after a long time in the background.
"AnkiDroid's collection" (opening AnkiDroid's own collection) is written and
tested below but not offered: Anki's backups drop the collection's lock.

## AnkiDroid's collection (2026-10-23)

A profile that opens AnkiDroid's own `collection.anki2` (`ankidroid.FOLDER`),
still hidden (`FOLDER_READY = False`). Fixes:
[fixes.md](fixes.md#sync-server-and-ankidroids-folder-preferences--advanced).

Host tests: 56 passing, 8 new ones: the background watch only for this mode,
close and reopen with AnkiDroid's changes (screens refreshed) and without
(left alone), a busy collection kept open, reopening while another process
holds it (retry, then success once released), operations started while
closed waiting for the reopen, and Anki's backup dropping the lock.

Emulator (API 37) with AnkiDroid 2.25.3 full, profile **DroidFolder**:

| Test | Result |
| --- | --- |
| AnkiDroid started over Kioku (`monkey`, the launcher's intent): AnkiDroid resumes before Kioku's onStop | ✅ Kioku closed it in onPause in 3–60 ms, before AnkiDroid's DeckPicker; no "Database Locked" (14 times) |
| Back to Kioku after AnkiDroid answered a card, AnkiDroid force-stopped in between | ✅ reopened, AnkiDroid's review there, screens refreshed |
| Back to Kioku while AnkiDroid still has it | ✅ retry dialog (8 of 8 trials); stays locked after 60 s; Try again after a force stop reopens it; all 14 answers in the revlog |
| Retry dialog → AnkiDroid app info… → Force stop → back to Kioku | ✅ after a fix (it crashed: see fixes) |
| Tools › Switch to AnkiDroid | ✅ closed first, AnkiDroid opened it |
| AnkiDroid answering cards while its lock was gone | ❌ **lost**: two answers never reached the file. Cause: Anki's backup (see below) |

Anki's backup reads `collection.anki2` through a second file descriptor
while SQLite has it open (rslib `maybe_backup` → `read_locked_db_file`), and
closing it drops the process's POSIX locks on the file, SQLite's exclusive
lock too. Confirmed on macOS (`test_anki_backup_drops_the_lock`): a second
process is locked out before `create_backup`, opens it after. AnkiDroid's
core does this on its automatic backups, so Kioku could open the collection
while AnkiDroid kept it open, and Kioku's close then deleted the `-wal` file
AnkiDroid was still writing to. Kioku can't detect it, so the mode stays
hidden until Anki's core (Kioku's and AnkiDroid's) keeps the lock.

Not done: big collection timings, Samsung M30s, device reboots.

## Syncing when switching apps, AnkiDroid's collection explained (2026-10-23)

Guide: [sync-server.md](manual/src/features/ankidroid.md#syncing-when-you-switch-between-kioku-and-ankidroid).

Host tests: 68 passing. New (`test_switchsync.py`, real sync server, a
second collection standing in for AnkiDroid): when it applies (phone's
server, automatic sync on, logged in), leaving sends the changes before
"AnkiDroid" syncs, nothing sent without changes or while an operation runs,
a needed full sync never done in the background (AnkiDroid's copy
untouched, Anki's own sync with its question on return), a failed sync
left for Anki to show, coming back syncs only after 2 s away, coming back
during the background sync, the background watch on and off. The Advanced
tab: "AnkiDroid's collection (not available)" shows the explanation and
changes nothing, a profile saved in that mode shows as its own collection
and opens it (with a message), automatic sync off is pointed out.

Emulator, profile **ServerTest** (AnkiDroid's media, phone's server):

| Test | Result |
| --- | --- |
| Kioku adds a note, AnkiDroid started | ✅ background sync 61 ms, done inside onPause (before AnkiDroid's first screen); 1.4 s for the first sync after Kioku starts (onPause stops waiting at 400 ms) |
| AnkiDroid gets the note | ✅ after tapping its Sync: its automatic sync runs only on start/exit and only if its last sync was more than 10 minutes ago |
| AnkiDroid answers a card and syncs, back to Kioku | ✅ Kioku's sync on return brought the review in |
| Profile saved as "AnkiDroid's collection" opens | ✅ its own collection, message says why |
| Tapping "AnkiDroid's collection (not available)" | ✅ the explanation (a scrollable window: a QMessageBox this tall was sometimes drawn squashed) |

## Remote desktop, Termux variant (2026-10-23)

Results in [termux/docs/remote-desktop.md](../termux/docs/remote-desktop.md#tested):
19 tests on the phone (`termux/tools/test_on_device.sh`) and the whole flow on the
emulator (VNC viewer and noVNC in Chrome, Anki moved there and back with a change
made remotely, battery prompt, locks, Power off). Fixes in
[fixes.md](fixes.md#remote-desktop-termux-variant).

## VoiceOver / first-run crash on iPadOS (2026-10-23)

GitHub issue: Kioku closed right after confirming the language on first
run (iPad, iPadOS 18.7.8, LiveContainer and SideStore). Two causes, fixes in
[fixes.md](fixes.md#runtime-platform): Qt's iOS accessibility (`qios-a11y-destroyed-object.patch`),
then, on iOS 18 only, WebKit's stack bounds for the main thread (`ios/src/main.mm`).

| Test | Result |
| --- | --- |
| BrowserStack App Live, iPad (iPadOS 18), dev-signed IPA, first run | ❌ before the fix: closed after Yes; same log as the issue |
| BrowserStack App Live, iPhone, first run | ❌ before the fix: same |
| BrowserStack iPad (iPad15,6, iPadOS 18.6), accessibility fix only | ❌ language step passed, then `JSC::sanitizeStackForVM` (`Kioku-2026-10-23-033444.ips`): the iOS 18 stack-bounds crash |
| Same, `RLIMIT_STACK` raised again in `main()` (build 2) | ❌ same crash (`Kioku-2026-10-23-034541.ips`); its registers show WebKit's bounds still 512 KB |
| Same, `JSVirtualMachine` created before Qt starts (build 3) | ✅ first run through to the main window, no crash report |
| iPhone 15 Pro Max (iOS 27.0.1), fresh install, VoiceOver off | ✅ (no accessibility events at all) |
| Same, VoiceOver on, before the fix | ❌ `Kioku-2026-10-23-082234.ips`: `EXC_BAD_ACCESS` in `QAccessibleButton::role` from `notifyAccessibilityUpdate` while the "Are you sure?" box is destroyed |
| Same, VoiceOver on, patched `libqios.a`, tapped by hand | ✅ language chosen, main window, no crash report |
| Same again from a fresh install, scripted (devcmd), VoiceOver checked on before each step | ✅ OK → "Are you sure?" → Yes → main window; Preferences opened and closed; a message box shown and closed with OK; 53 accessibility events, no new crash report |
| iPhone (iOS 27.0.1), build 3 | ✅ starts, deck browser; a `evalWithCallback` round trip through the main web view returns its result. `RLIMIT_STACK` there is 1,032,192 (whole stack) and lowering it fails with `EINVAL`, which is why iOS 27 never crashed |
| "My Mac (Designed for iPad)" | not usable for this: builds, but a development-signed iOS app can't be launched from the command line (Gatekeeper "damaged", or "Terminated due to code signing error" under lldb); only Xcode's Run does |

The patched build exports the same symbols as Qt's object, and the linked
app's `notifyAccessibilityUpdate` is the patched one (169 instructions, 144 in Qt's).

### Crash sweep (`ios/tools/smoke.sh`, 2026-10-23)

`tools/smoke.sh` runs `tools/smoke.py` in the app: About, Browse, Add, Stats,
Preferences, Note Types, Filtered deck, Study Deck, Empty Cards, Export,
Add-ons, Deck Options, Check Database, Check Media, Sync (login), study a
card, answer, undo, deck list, Switch Profile and Back, each closed the way
Back closes it. Each step logs `SWEEP <n> <name>` before it starts, so after a
crash the log shows the step; the script prints only the summary and new
crash reports.

| Build (iPhone 15 Pro Max, iOS 27.0.1) | Result |
| --- | --- |
| 4 (Back on the profile window reopens the last profile) | ✅ 22/22, back on profile User 1 |
| 5 (also `os._exit` after `aqt.run()`) | ✅ 22/22; Quit (`unloadProfileAndExit`) ends the app without a crash report |

The sweep can't run on BrowserStack (no `devcmd` there): iOS 18 is checked by hand there.

## Release check for 0.2.2 (2026-10-23)

Host tests: 68 passing. Samsung M30s (Android 11), build from `d3ebc69`
installed over the old one (data kept), profile User 1 (258,430 cards):

| Test | Result |
| --- | --- |
| Start-up, collection opens | ✅ |
| `sweep.sh`: 12 windows full screen, nothing wider than the screen | ✅ |
| Reviewing: question, answer; Edit menu has Edit Current and More | ✅ |
| `{{tts}}` player: Samsung engine, 4 voices | ✅ |
| Sync server: start, HTTP 200 from `http://127.0.0.1:8080/health`, stop (setting not saved) | ✅ |
| Browse: search typed with the keyboard, Enter runs it | ✅ |
| Home, then back from the launcher | ✅ |
| File › Switch Profile, then Back: last profile reopens | ✅ |
| File › Exit: process ends, no crash in logcat; relaunch works | ✅ |

Not repeated on a device this round: iOS, Termux variant, AnkiDroid's media.

Advanced features, same day:

| Test | Result |
| --- | --- |
| AnkiDroid's media (M30s, AnkiDroid 2.25.3 full): new profile in that mode opens with `/storage/emulated/0/AnkiDroid/collection.media` | ✅ |
| A note with an image: the file is written into AnkiDroid's folder; AnkiDroid's `collection.anki2` and `collection.media.db` unchanged | ✅ |
| Check Media: AnkiDroid's 326 files count as unused, deleting them stays off by default | ✅ |
| Termux remote desktop: `termux/tools/test_on_device.sh` on the emulator | ✅ 19 tests |

Not repeated: the live VNC session (same emulator build as the 2026-10-23
round) and AnkiDroid syncing through the phone server on the M30s (it would
change AnkiDroid's own sync settings). The M30s's Termux variant is signed
with another key, so the new build can't be installed over it without
deleting its data.

Test mistake: cleaning up the test profile with `mw.pm.remove(name)` deleted
the *loaded* profile's folder (Anki's `remove` ignores `name` for the folder,
and on Android falls back from the trash to `rmtree`). User 1 was restored
from its `.colpkg` (258,430 cards, 27,195 media files).

## AMBOSS add-on, full screen, update prompt (2026-10-23)

From an iPad report (iPadOS 18.7.8, iPad13,4): AMBOSS login failed, View ›
Full Screen could not be left, the "Anki updated" prompt at first start.
Host tests: 74 passing (new: `test_webengine.py`, `test_mainsplit.py`).
Android APK builds; not run on Android this round (no device attached).

iPhone 15 Pro Max (iOS 27.0.1), AMBOSS add-on 1044112126, test account:

| Test | Result |
| --- | --- |
| Add-on loads without an error; AMBOSS menu, toolbar button, Qbank widget on the deck list | ✅ |
| Login dialog: email + password, Log in → token stored, "Mobile Support" prompt (answered Not now: Yes rewrites card templates) | ✅ |
| Side panel opens on `next.amboss.com` logged in (auth cookie reached WKWebView) | ✅ |
| Side panel, portrait: stacked under the deck list, ▲ expands it to the full height, ▼ splits again | ✅ |
| Cookie banner in the panel: Reject all | ✅ |
| Sample deck "AMBOSS Test" (20 medical cards, `build-testdata/amboss/`): terms underlined while reviewing | ✅ |
| Term pop-up (ADPKD): fits the screen width, images scaled, scrolls down to its end | ✅ |
| Top bar: Decks, Add, Browse, Stats, Sync and the AMBOSS button in one row | ✅ |

Also on the iPhone, full screen: the strip above the top bar highlighted
with an arrow to Anki's tooltip, its text whole (screenshot in the manual,
`using/native.md`, AMBOSS disabled for it); a real finger tap on the strip
left full screen (seen in the event log); scripted taps on the highlight and
the strip leave it; one View › Full Screen enters it again. Host tests: 77.

Not tested: an iPad (the side-by-side layout is host-tested only, and the
narrow-screen CSS applies under 600 px only), a real finger tap on a term
(a scripted hover was used), the update prompt at a fresh first start. The
login was lost once when a reinstall killed the app in the foreground: Kioku
saves the profile when the app leaves the foreground, as a user's app would.

Later the same day full screen changed: the strip margin (24 pt where the
safe area was smaller, which moved the view on an iPad), the tap above the
top bar and the highlight are gone. A swipe to the right on any page opens a
confirmation, Exit Full Screen or Cancel (a long press on the bottom bar was tried first
and dropped: it could press the button under the finger). iPhone 15 Pro
Max, build 7, synthetic touch events in the page:

| Test | Result |
| --- | --- |
| Enter full screen: menu bar hidden, layout unchanged, tooltip "Swipe right to exit full screen" | ✅ |
| Swipe right on the deck list, the review card, the bottom bar → "Exit full screen?" centred as a card, the hint tooltip closed | ✅ |
| Exit Full Screen leaves it; Cancel stays; one View › Full Screen enters it again | ✅ |
| Swipe left, vertical swipe, swipe right outside full screen: nothing | ✅ |
| Swipe right while the page can still scroll that way: the page scrolls, no dialog (the deck list is 18 px wider than the screen with AMBOSS's Qbank widget) | ✅ |

Screenshot of the dialog in the manual (`using/native.md`). Host tests: 79.
Not tested: a real finger swipe, an iPad (IPA build 7 for
BrowserStack), Android.

## Anki 26.09.3 update (2026-10-23)

What changed upstream that Kioku depends on: `python3 -I shared/tools/anki_drift.py`
(26.08.1 → 26.09.3: `setupGL`, `AnkiApp.__init__`, `AnkiQt.__init__`,
`AnkiWebView.__init__` changed; the sync server patch applies). Fixes in
[fixes.md › Anki updates](fixes.md#anki-updates).

| Check | Result |
| --- | --- |
| Host tests (`shared/tests/run.sh`, rsbridge from 26.09.3 with the reworked sync server patch) | ✅ 79 passed |
| iOS (iPhone 15 Pro Max, iOS 27.0.1): starts, log says `Starting Anki 26.09.3` | ✅ (the first build failed with the build hash error in fixes.md, fixed) |
| iOS: Statistics' web view gets the `Authorization` header for `mw.serverURL()` and draws its graphs | ✅ |
| iOS: crash sweep (`tools/smoke.sh`) | ✅ 22/22, back on User 1 |
| iOS: Browse, then Add: `aqt.dialogs.activeWindow()` (26.09's focus tracking, used by the editor's Fields and Cards buttons) is Add | ✅ |
| iOS: `syncserver_start()` on a free port answers `/health`, `syncserver_stop()` closes the port | ✅ |
| Android (emulator, swiftshader): starts with `Starting Anki 26.09.3`, profile User 2 with its add-ons | ✅ |
| Android: Statistics gets the `Authorization` header and draws its graphs; Browse, then Add: `activeWindow()` is Add; sync server start, `/health`, stop | ✅ |
| Android: crash sweep (`ios/tools/smoke.py` through `devcmd.sh`) | ✅ 22 steps, no crash. Check Database showed "wrapped C/C++ object of type ProgressDialog has been deleted": on the emulator it runs well over the sweep's 2.5 s step, and the sweep closed its progress window. Run alone, it finishes without an error |
| Termux variant: `anki_26.09.3_aarch64.deb` built in a 4-core Codespace (29 min cold; later the `anki` workflow on Actions: 16 min, 7 min 44 s cached, [building.md › Building the anki package](../termux/docs/building.md#building-the-anki-package)), released as [anki-26.09.3](https://github.com/krmanik/termux-packages/releases/tag/anki-26.09.3); paths under `./data/data/com.termux`, Depends the same as 26.08.1's | ✅ |
| Termux (emulator, swiftshader, APK `0.1.0-anki26.09.3`): starts with `Starting Anki 26.09.3`, `aqt.appVersion` 26.09.3, Qt 6.11.2, Python 3.14.8, empty crash.log | ✅ |
| Termux: phone scale reaches Qt before the QApplication (`launch_anki.py`'s setupMeta hook): `QT_SCALE_FACTOR`, `pm.uiScale()` and the window's device pixel ratio all 2.25 (the app's scale for 420 dpi), screen 480×1067 logical | ✅ |
| Termux: Deck Options (web view, fits the width), Add (editor loads, `activeWindow()` is Add, a note added through the dialog and removed again), Statistics (draws) | ✅ |
| Termux on the Samsung M30s | not tested: not connected |

## Preferences tabs on phones, fresh installs (2026-10-23)

Reported from TestFlight (0.2.2): Preferences' tabs ran past the screen, with two small scroll arrows. The two performance overlays in the same screenshot are the tester's Metal HUD (iOS Settings › Developer › Graphics HUD); iOS draws one per window that renders, so Preferences and the login card each got one. Kioku's Info.plist and launch environment don't turn it on.

The tabs now sit in a strip that scrolls sideways with a swipe (a first try with a drop-down list of the pages was replaced at the user's request).

| Check | Result |
| --- | --- |
| Host tests (`shared/tests/run.sh`, `test_tabs.py`: strip above the pages, wider than its view, follows the tabs both ways and scrolls the chosen tab into view, hidden tabs stay hidden, Qt's tabs again when wide enough, one strip after refits) | ✅ 85 passed |
| iPhone 15 Pro Max (iOS 27.0.1): TestFlight 0.2.2 uninstalled, dev build installed fresh; first run: language list, "Are you sure?", main window on User 1 (`Starting Anki 26.09.3`) | ✅ |
| Android emulator: fresh install, first run tapped through with adb, main window on User 1. Qt shows "Are you sure?" as Android's own dialog, so clicking the hidden Qt box from a script doesn't answer it | ✅ |
| Android emulator: Preferences shows the strip without arrow buttons; an adb swipe scrolls it to Backups … Advanced without changing the page; a tap on Experiments shows Experiments | ✅ |
| iPhone (build installed over, data kept): Preferences shows the strip (824 px of tabs in a 408 px view); choosing Advanced scrolls it to the end | ✅ (chosen from a script; a finger swipe on iOS not tried by me) |
| Samsung M30s | not tested: not connected |

## Flicker and wide pages on phones (2026-10-24)

Reported with an iOS screen recording (iPhone XS Max/11 Pro Max size, no description). The tester's add-ons add deck-list columns, so the list ran past the right edge; they pinched out (the page shrank into a dark frame and sprang back), panned the whole page sideways, then turned the phone to landscape. At 45–47 s, Sync showed a full-screen "Syncing… / Checking…" window and the deck list then came back drawn at desktop width for a frame. The dim look of the recording is the recording itself (the status bar is dimmed too).

Reproduced on the iPhone and the Android emulator with the user's add-ons (Enhance main window 877182321, Custom background 3.0 1210908941 with the user's photo, Review Heatmap 1771074083) on a new "User 2" profile on the iPhone (the old User 2 backup, `build-testdata/colpkg/User2.colpkg`, imported into it). Frames caught with timed in-app screenshots every 40 ms (iOS) and `adb shell screenrecord` (Android). Code loaded into the running apps (no rebuild).

| Check | Before | After |
| --- | --- | --- |
| iPhone: deck list refresh | ~0.5 s of the list drawn at 980 px (tiny), then snaps | straight to the phone layout |
| iPhone: review → deck list, deck list → overview | — | straight to the next page (entering review shows one empty frame while the card loads, as before) |
| iPhone + emulator: progress window (as in a sync) | full screen with "‹ Back", then a blank white frame (Android) | small card with Cancel over the screen; Cancel sets `want_cancel()` and the card stays until the task stops |
| Emulator: three deck list refreshes | each one ~0.5–0.8 s with desktop column widths, then a jump | no jump |
| iPhone: page width on the deck list with the three add-ons | 1795 px (screen 430) | 430 px; deck table scrolls inside its box |
| iPhone: Review Heatmap on deck list and overview | 636 px SVG, off screen | scaled to 415 px / 370 px; still fits after its year button redraws it |
| iPhone: Preferences | — | opens (a 403 "Unexpected API access" seen once came from reloading `webengine.py` inside the running app during testing; a clean start and the final reload don't show it) |
| Host tests (`shared/tests/run.sh`, new: `test_progress.py`, `test_screenedges.py`, `with_viewport` in `test_webengine.py`) | | ✅ 90 passed |
| iOS pinch-out bounce | | not testable from a script (`bouncesZoom` off) |
| Bottom bar to the screen edge, iPhone | bar ended 34 px above the bottom; strip of window colour below | bar 95 px (61 + 34) reaches the bottom (931 of 932); the photo runs to the edge; buttons above the home indicator, in the deck list and in review (answer buttons) |
| Bottom bar to the screen edge, emulator | bar ended 24 px above the bottom | reaches the bottom (913 of 914); buttons where they were |
| Bar hidden in review (Anki's `BottomWebView.hide()`) | | window bottom margin back to 34 px; shown again: bar to the edge |
| iPhone landscape (rotated by the user, then from a script with `requestGeometryUpdate`, both sides) | bottom bar to the edge, but 59 px strips of window colour left and right | views fill the width (932 of 932), the photo too; card text, deck list, Edit/More buttons and the menu bar ("File" at 65 px) clear of the notch; bottom bar padded 20 px |
| iPhone back to portrait | | side padding and menu spacers back to 0, bottom 34 |
| Emulator landscape (`user_rotation 1`) | | no side insets (no cutout), bottom bar to the edge |

Not changed: the web view lags behind the window for a moment while the phone rotates; add-on layouts themselves (Custom background crops the photo separately in the top bar, main view and bottom bar; an add-on's overview stats squeeze words) are for their developers.

## Accessibility-service freeze, Android (2026-10-24)

Reported on a OnePlus CPH2447 (Android 16) with Kioku 0.2.2 and 0.2.3: opening Preferences or Tools froze the window, then an ANR kill; accessibility services on (Bitwarden autofill, Join, Sleep as Android), TalkBack off. All 8 ANR traces show the same cycle: Qt's thread in `KiokuBridge.onUiThread` (`webview.title`) → `FutureTask.get`, the UI thread in `QtNativeAccessibility.populateNode` → `QLatch::waitInternal`. The crash buffer also has the `qFatal` abort in the patched `eglSurface()` under a menu popup.

Emulator (Android 16 image), Switch Access turned on as the accessibility service (`settings put secure enabled_accessibility_services …SwitchAccessService`), native Kioku, OpenGL video driver. With the Software driver every accessibility call bails out early (`no valid surface`), so no repro there.

| Check | Without the protector in `onUiThread` (same build otherwise) | Fixed build |
| --- | --- | --- |
| Start-up | blank window, ANR on the first tap; dropbox `data_app_anr` trace shows the reported cycle (`childIdListForAccessibleObject` → `QLatch` vs `onUiThread` → `FutureTask.get`) | deck list, 3 of 3 launches |
| Stress: `webview.title` from a 0 ms `QTimer` (146k calls) with Tools menu and Preferences opened | — | no ANR; 12–92 accessibility queries per run gave up (`accessing main thread could lead to deadlock`) where they used to block; slowest call 1.05 s (during start-up) |
| Tools menu, Preferences | — | open; app answers dev commands throughout |

Not covered: a password manager itself (none on the emulator); the reporter's phone.

## Issue #1 follow-up and issue #4: interface size, keyboard flash, Termux Advanced, custom remote size (2026-10-25)

GitHub issue #1 (after the accessibility fix: Termux has no Advanced tab, User interface size does nothing in either variant, remote desktop has only four sizes) and #4 (native Android: opening and closing the keyboard in the add and edit screens flashes black). Emulator (Android 17 arm64, `swiftshader_indirect`), cold-booted with `hw.keyboard = no` so Gboard shows a full keyboard; add-ons removed from the native profile. Keyboard runs: `screenrecord` while tapping a field and pressing Back twice, frames resampled to 60 fps, a frame counted black when a full-width band is under 25 of 255 grey.

| Check | Before | After |
| --- | --- | --- |
| Native: User interface size 150%, restart | `QT_SCALE_FACTOR` 1.0, nothing changed | 1.5: title bar, menus and Preferences larger, page text 150% |
| Native: Preferences at 150% | User Interface and Distractions rows drawn over each other | each tab page scrolls with a drag; range 50-200% |
| Native: Add window, keyboard open/close | black strip above the keyboard 100-400 ms on every open | 0 of 26 opens (last three builds); Tags and buttons stay above the keyboard (they used to end up under it after about 0.5 s) |
| Native: Browse, editor field near the bottom | black block where the editor was, every open | 2 of 8 opens show 50-100 ms of black inside the enlarged editor (Chromium drawing its new size), otherwise none |
| Native: reviewer, type-in answer box | no black | no black (5 of 5); the main window keeps Chromium's own keyboard handling |
| Native: window sweep (`tools/sweep.sh`, 12 windows) | | all open full screen; only Qt's hidden Preferences tab bar reported as wider than the screen (the swipe strip replaces it) |
| Host tests (`shared/tests/run.sh`, new: `test_syncserver_process.py`) | | ✅ all passed, 3 new |
| Termux: Preferences | 7 tabs | Advanced is the 8th; User interface size 50-300% |
| Termux: User interface size 150%, Preferences closed, app force-stopped, started again | back to 200% (the setting was never saved) | 150%, `QT_SCALE_FACTOR` 1.5 |
| Termux: sync server from the Advanced code (Termux's Anki has no `syncserver_start`) | — | child process listens on 18080, `/health` 200, a collection logs in and uploads, stop ends the child |
| Termux: remote desktop at Custom 2388 × 1668 (`parse_resolution("2388 x 1668")`) | sizes outside the four were refused | Xvfb at 2388 × 1668, RandR modes added (2388x1668 first), Anki's screen 2388 × 1668; back on the phone afterwards |
| Termux: Advanced › AnkiDroid's folder (stand-in `/sdcard/AnkiDroid` with a collection and `collection.media`) | — | All files access read from Android (`Environment.isExternalStorageManager`: ✗ before `appops … allow`, ✓ after; listing shared storage had said ✓ without it); "AnkiDroid isn't installed" (versions through `ankidesk:apps/…`); Find picks the folder; AnkiDroid's media: the profile opens with `/sdcard/AnkiDroid/collection.media`, its own collection |
| Termux: User interface size on the remote screen | always 100% | 175% saved as `kioku_remote_uiScale`; the phone's 150% unchanged |
| Termux: `tools/test_on_device.sh` (test_remote, new resolution tests) | | ✅ 26 passed |

Not covered: AnkiDroid itself in the Termux variant (not on the emulator); a physical phone (the emulator draws with SwiftShader, so Qt's frames are slower than on a phone and the delays were tuned there); iOS (the scale change is shared code; the keyboard changes are Android only).

## Crash on a tap, TestFlight 0.2.2 (126) (2026-10-25)

Crash report from a tester (iPhone18,3, iOS 27.0.1): `EXC_BAD_ACCESS` at
`0x8` during a touch, in Qt's text-selection gesture recognizer, with a null
focus object. Fix: [fixes.md](fixes.md#runtime-platform)
(`qios-null-focus-object.patch`, upstream in Qt 6.11.2 since). iPhone 15 Pro Max, iOS 27.0.1, dev builds.

| Test | Result |
| --- | --- |
| Report symbolicated with the archive's binary (same UUID `6F3F22D9…`) | `querySelection()` + 68 ← `-[QIOSSelectionRecognizer acceptTouchesBegan:]` ← `-[QIOSLoupeRecognizer touchesBegan:withEvent:]`; the fault is `ldr x8, [x0, #0x8]` in `QCoreApplication::sendEvent` with `x0` = `focusObject()` = null |
| Looking for the trigger: a focused line edit's dialog closed with `deleteLater`, `sip.delete`, hide and delete together, `setWindowFlags`, `windowHandle().destroy()`; `aqt.utils.getText`; Add › Deck (Study Deck) picked; Browse search then Back; Preferences spin box then close; the editor's web view made first responder | ✅ every time the recognizers went away with the focus (checked through UIKit's `gestureRecognizers`, sampled 0-1000 ms after the change) |
| A minute of real taps (Browse search, editor fields, keyboard swiped down, Study Deck filter, text boxes then the deck list) with a monitor for "focus object null while Qt's recognizers are attached" | ✅ no such state, no crash; two changes to a null focus, both signalled |
| Forced: a text field focused, then `QGuiApplicationPrivate::focus_window` set to null in memory (what `QWindowPrivate::destroy()` does), one tap, unpatched build | ❌ crash, `Kioku-2026-10-25-121855.ips`: the reported stack (`querySelection()` ← `-[QIOSCursorRecognizer acceptTouchesBegan:]`) |
| Same with the patched `libqios.a` (the app's `querySelection` now starts with `cbz` on `focusObject()`) | ✅ several taps on the deck list, the dialog's text box and buttons; app kept running, no new crash report |

Not found: which path in the tester's app left the focus null without the
signal. The patch covers every such path for this crash.

## Incremento add-on, all variants (2026-10-28)

[Incremento](https://ankiweb.net/shared/info/1013949798) (incremental
reading, 2026.10.26) failed to load everywhere: `No module named
'PyQt6.QtPdf'`. Fixes in [fixes.md](fixes.md) and, for Termux,
[termux/docs/building.md](../termux/docs/building.md) ("Known gaps").
Tested on the iOS Simulator (iPhone 16 Pro) and the Android emulator
(Android 17), both native apps and the Termux variant.

| Step | iOS Simulator | Android (native) | Termux |
| --- | --- | --- | --- |
| Add-on loads (menu, timer bar, Topics deck, getting-started guide) | ✅ | ✅ | ✅ (also needed the accessible-name fallback) |
| `QPdfDocument`: page count, sizes, title and dates, text, render, worker threads, error codes | ✅ PDFKit | ✅ PdfRenderer (text from Android 15 on) | ✅ real bindings |
| Import a PDF as a topic card (cover image, text) | ✅ | ✅ | ✅ (through PyMuPDF) |
| Review it: pdf.js reader in the dock, "PDF 1 / 2" | ✅ | ✅ | ✅ |
| Reader stacked under the main view in portrait, beside it in landscape | ✅ | ✅ (rotated both ways) | ✅ |
| Optional tools (PyMuPDF, Tesseract, DjVuLibre, FFmpeg) | PyMuPDF ✅ built in; the others – (iOS can't start processes) | PyMuPDF ✅ built in; the others – | ✅ installed from the Termux repositories with the app installer (`python-pymupdf tesseract djvulibre`); FFmpeg is in the runtime |

On the iPhone 15 Pro Max (device build with the stack fix): objects freed
on the main thread are deallocated and an sqlite3 commit after a finished
statement works; `QPdfDocument` over PDFKit gives page count, sizes,
title, text and renders; Incremento installed from AnkiWeb loads, imports
a PDF as a topic card with its cover, and the review shows the pdf.js
reader stacked under the main view ("PDF 1 / 2"). Its dependency setup
dialog lists PyMuPDF, Tesseract, FFmpeg and DjVuLibre as missing (before
PyMuPDF was built in). Landscape wasn't tried on the phone.

PyMuPDF built in (`shared/tools/build_pymupdf.sh`): on the iPhone and the
Android emulator `import pymupdf` takes 0.5 s, writing, reading, text,
words and rendering work, Incremento's dependency window shows PyMuPDF as
installed and its PDF import extracts the text through it. The reader's
tools on the iPhone: Read to here and Bookmark save; Extract with a
selection highlights it and fills the Add Card panel, which is now a tab
beside the reader; Annotate's colours and capture tools show once the
reader is expanded (▲ in its title bar). Sizes: APK 50.3 → 70.1 MB; iOS
binary +35 MB unstripped.

On the Simulator the add-on reports Tesseract and FFmpeg as found: the
Simulator sees the Mac's Homebrew. Two Incremento instances on one device
(native app and Termux variant) can't both open its browser bridge
(127.0.0.1:8766); the second logs "Address already in use".

## Programs and packages for add-ons, both native apps (2026-10-29)

What's bundled and why: [addon-deps.md](addon-deps.md). Three test scripts
in `shared/programs`, run inside the app through devcmd (Android emulator,
Android 17, 16 KB pages; iOS Simulator, iPhone 16 Pro) and on the Mac
(`python3.14 shared/programs/test_programs.py build/programs/macos/lib`,
every program run inside the process, as on iOS):

| Script | What | Mac | Android | iOS Simulator |
| --- | --- | --- | --- | --- |
| `test_programs.py` | ffmpeg/ffprobe (every encoder, pipes as pydub uses them, `cwd=`, `shell=True`, `terminate()`, `timeout=`, runs at once), lame, mecab (two open at once, a line at a time), kakasi (Japanese Support's way; a second one while it stays open), tesseract (file, stdout, stdin, tsv), espeak-ng, cwebp, dwebp | 51/51 | 51/51 | 51/51 |
| `test_packages.py` | numpy (linalg, fft, random), Pillow (PNG, JPEG, WebP, GIF, FreeType), cryptography, pyOpenSSL, jieba | – | 15/15 | 15/15 |
| `test_addons.py` | Japanese Support's mecab and kakasi controllers, AJT Media Converter's `FileConverter` (image to WebP with cwebp, audio to Opus with ffmpeg), AnkiOCR's OCR (pytesseract) | – | 7/7 | 7/7 |

The add-ons came from AnkiWeb (Anki's update check replaced the copies from
the dump with the current packages, with their own `support/` binaries,
which Kioku swaps for its own). AnkiOCR's package fails to load on any Qt 6
Anki (its GUI imports PyQt5); its OCR module was loaded on its own.

Found on the way and fixed:

- Android refused cryptography's Rust library (4 KB pages on a 16 KB-page
  device), then couldn't resolve its Python symbols (PyO3's abi3 build
  doesn't link libpython): `RUSTFLAGS` in `build_wheels.sh`.
- AnkiOCR: `KeyError: 'Android'` (its tesseract table has Windows, Darwin,
  Linux; `platform.system()` changed in Python 3.13), then pytesseract's
  `pkgutil.find_loader` (removed in 3.14): `kioku/patches.py`.
- iOS: a second kakasi waited forever while Japanese Support kept its own
  open, freezing the app: runs now give up their lock while they wait for
  input, their globals saved (`kioku_prog.c`).
- iOS Simulator: espeak-ng found no data (its 160-byte path buffer cut the
  bundle path).
- kakasi 2.3.6 misread Japanese Support's dictionaries (older format): read
  6 bytes off.

Which AnkiWeb add-ons need libraries or programs Kioku doesn't bundle: [addon-deps.md](addon-deps.md).

## AnkiWeb login, empty deck list, Android (2026-10-30)

Emulator (Android 17, `-gpu swiftshader_indirect`), test AnkiWeb account of
40,359 cards. Not run on a physical phone.

| Test | Before the fix | With the fix |
| --- | --- | --- |
| User 1 (41 local cards): Sync, log in, conflict, Download | works | not repeated |
| New empty profile: Sync, log in, "Download from AnkiWeb?", Yes | works | not repeated |
| New empty profile: Preferences, log in, "sync now?", Yes | reaches the same prompt | not repeated |
| Empty profile: Yes, then Home after 3 s, back after 60 s | **fails**: network error, 0 cards, empty list | works: 40,359 cards, `procState=FGS`, no firewall change for the app |
| Service during and after a sync | none | `dataSync` foreground while syncing, gone after |
| Message open while the profile switches | **unseen**, blocks taps | drawn above the deck list |
| User 2 (258,431 local cards): log in, conflict, Cancel | not run | cards unchanged |
| Restart after the download | decks still there | not repeated |
| Home and back, 8 times | not run | no crash |

The diagnosis: `dumpsys netpolicy` logged `10232-background-default` 8 s after
Home and `10232-background-allow` on the way back.

Open:

- One SIGSEGV on the way back from Home, before the fix, in the emulator's GPU
  driver (`libEGL_emulation.so`, `createNativeSync`, from `eglSwapBuffers`).
  Not seen again in 8 cycles. On restart the profile was still logged in and
  empty, and asked to download again.
- The box shown while waiting for media sync when a profile closes is cut off
  on the right, with an empty log line (`19:02:14: , ,`).
- A dialog's first frame can be black (seen once, on the conflict dialog).

## Extra files for add-ons, downloaded on demand (2026-10-31)

jieba, Tesseract's languages and eSpeak NG's data left the app bundles
(`kioku/packs.py`, `shared/tools/packs.py`); the zips are on the `packs`
branch and served from raw.githubusercontent.com. Also left out: test-only
extension modules (CPython `_test*`, `xxlimited*`, numpy `*_tests`, `_simd`,
`PIL._imagingtk`) and `.pyi` stubs.

| Size | Before | After |
| --- | --- | --- |
| iOS app, installed (dev build) | 325 MB | 251 MB |
| iOS app, zipped (≈ download) | 127 MB | 88 MB |
| Android APK | 142 MB | 102 MB |
| Packs (jieba, Tesseract, eSpeak) | — | 5.2 + 10.0 + 9.2 MB |

jieba's pack leaves out `lac_small/` (paddle mode, needs paddlepaddle) and
the `.p` pickles (read only on Jython): 37 → 18.5 MB unpacked. Checked on
the Mac: cut, POS tags, keyword extraction, `importlib.metadata`.

| Test | iPhone 15 Pro Max | Emulator (Android 17) |
| --- | --- | --- |
| Start with Incremento installed: offer for Tesseract names the add-on | works | works |
| Download from the offer; `tesseract --list-langs` lists the 6 languages from the pack | works | works, with Home pressed right after Download |
| `import jieba` with no pack: second offer queued after the first | works | — |
| Download, then `jieba.lcut` without a restart | works | works |
| Install an unknown add-on (`.ankiaddon`, lazy `import jieba`): offer at once | — | works ("Chinese Segment Probe needs…") |
| Not now: remembered; Extra Files shows "(1 needed)" on the add-on | — | works |
| Tools › Add-ons › Extra Files: needed first, Download / Remove, sizes | works | works (real taps) |
| eSpeak from the pack (`espeak-ng -v zh/ja --ipa`) | works | works |
| Remove: status back to "Not downloaded" | works | works |
| Foreground service while downloading (`ankiwebsync.hold`) | n/a | runs; notification hidden only because the emulator never granted POST_NOTIFICATIONS |

Host tests: `shared/tests/test_packs.py` (scan, sys.path and variables,
import offer, download over a local HTTP server, checksum and path checks,
updates, remove, Not now, dialog and Add-ons button, shipped manifest).

Second round (same day): Pygments as a pack (1.2 MB); rsbridge with fat LTO
(the translations were in the binary twice); local symbols stripped from the
iOS binary and frameworks, Android wheels' `.so` files stripped.

| Size | Start | After packs | After round 2 |
| --- | --- | --- | --- |
| iOS app, installed | 325 MB | 251 MB | 215 MB |
| iOS app, zipped | 127 MB | 88 MB | 80 MB |
| Android APK | 142 MB | 102 MB | 94 MB |

| Test | iPhone | Emulator |
| --- | --- | --- |
| numpy, Pillow, cryptography, pymupdf import and run (stripped modules) | works | works |
| Collection opens, `tr` strings (LTO build), ffmpeg, tesseract | works | works |
| `markdown` with codehilite (probes pygments) outside add-ons: no offer | works | — |
| Pygments pack from GitHub, then `highlight()` | — | works |
| HTTPS after `pm trim-caches` (CA bundle no longer in the cache) | n/a | works; failed before the fix |

## Add-ons that use bundled programs, in the app's own screens (2026-10-31)

Emulator (Android 17), add-ons installed from AnkiWeb (current packages, with
their own `support/` binaries, which Kioku swaps), profile AddonTest, note
type with Expression, Reading, VocabKanji, … fields. Each feature was run
the way a user reaches it: the Add window's editor (field focus lost, toolbar
buttons, paste), the Browser's menus on selected notes, the reviewer, the
Tools menu, the image occlusion editor. Scripts drove the screens through
devcmd (focus sent as the WebView sends it on a tap).

| Add-on | Where | What ran | Result |
| --- | --- | --- | --- |
| Japanese Support (3918629684) | editor: focus lost | mecab reading into Reading | works |
| | Browser › Edit › Bulk-add Readings | mecab | works |
| AJT Japanese (1344485230) | editor: focus lost | furigana and pitch accent (mecab, its pitch table) | works |
| | Browser › AJT Japanese: Bulk-generate | furigana, pitch | works |
| | reviewer | answer shows the generated furigana and pitch | works |
| JapaneseFurigana (678316993) | editor toolbar button | furigana for the focused field (mecab) | works |
| | Browser › Bulk Generate Furigana | mecab, chosen source/destination fields | works |
| SimpleFurigana (1444055400) | editor toolbar button | its mecab works; the button finds no selection | **add-on**: its script uses jQuery and the page's selection, both gone from Anki's editor since 2.1.50 (desktop too) |
| Syntax Highlighting NG (566351439) | editor toolbar button | Pygments (pack) into the focused field | works |
| AJT Media Converter (1151815987) | editor: paste an image | cwebp → `.webp` | works |
| | Browser › Bulk-convert | image → WebP (cwebp), WAV → Ogg/Opus (ffmpeg) | works |
| AnkiOCR, Shige's fork (546383173) | Browser › Cards › AnkiOCR › Run | tesseract text into the image's `title` | works ("Kioku reads this text") |
| Auto Image Occlusion (1414192727) | Add › Image Occlusion, its Auto-detect button | tesseract word boxes → regions | works |
| AnkiMorphs (472573498) + ankimorphs-japanese-mecab (1974309724) | Recalc (toolbar) | Japanese morphemizer (mecab), `am-*` tags on 9 notes | works |
| FrequencyMan (909420026) | its Japanese tokenizers (used when it reorders) | AnkiMorphs MeCab, AJT Japanese MeCab | works |
| KanjiVocab (1600796261) | its splitter | mecab with Japanese Support's dictionary | works |
| MeCab UniDic Dictionary (13462835) | its MeCab process | mecab with UniDic | works |
| Migaku Kanji GOD (1872210448) | start-up, reviewer (answer hook), its MeCab parser | `mecab-linux` | **failed to load** before the fix (name not swapped), works after |
| Migaku Japanese (278530045), AwesomeTTS (814349176) | — | — | not on AnkiWeb for 26.09; the old copies import PyQt5 (desktop too) |

Not run: Batch Download Pictures From Google Images (PIL, needs Google
search results), Incremento (tested 2026-10-28).

Found and fixed (docs/fixes.md, Add-ons):

- Program copies named `mecab-linux` / `-macos` / `-windows.exe` weren't
  swapped (Migaku Kanji GOD).
- Android emptied the cache folder while the app ran (the emulator's storage
  was full) and took the program links with it: every program failed until a
  restart, Anki dropped Japanese Support's focus-lost hook after the error,
  and a later import of Kanji GOD aborted the app (`QThread: Destroyed while
  thread is still running`, from its earlier failed import). The links moved
  to the config folder; checked on a fresh build.
- Qt's Android clipboard couldn't hold links (Qt 6.11.0 bug); an https link
  copies and reads back now. `file://` links are refused by Android itself,
  and Qt on Android has no images on the clipboard: the paste test fed the
  editor the same data a paste gives it.

Seen, not changed: Anki's `send2trash` fails on Android's shared storage
(`.Trash-<uid>` missing) when an add-on is replaced; Anki deletes the old
folder instead, so updates work. Programmatic `focusField()` doesn't reach
Python without a tap (the WebView has no native focus); users tap fields.

### Same add-ons on the iOS Simulator (2026-10-31)

iPhone 15 Pro Max simulator (iOS 26.4), the same 13 add-ons installed from
AnkiWeb, profile AddonTest, note type "Japanese (Kioku test)". The same
screens were driven as on Android: the Add window's editor (focus lost,
toolbar buttons with the field focused and its text selected in the
WebView, image paste), the Browser's menus, Tools › Recalc, the Image
Occlusion editor, the reviewer. Programs run inside the app on iOS.

| Add-on | Where | Result |
| --- | --- | --- |
| Japanese Support | editor: focus lost (mecab, kakasi); Browser › Bulk-add Readings | works |
| AJT Japanese | editor: focus lost (furigana, pitch); Browser › Bulk-generate; reviewer shows the pitch | works |
| JapaneseFurigana | editor button; Browser › Bulk Generate Furigana | button **failed** before the fix (below), works now; bulk works |
| Syntax Highlighting NG | editor button, code from the clipboard (Pygments) | works |
| AJT Media Converter | image paste → WebP (needs its "copy_paste" option, off by default); Browser › Bulk-convert: images → WebP, WAV → Ogg/Opus | works |
| AnkiOCR (Shige) | Browser › Run AnkiOCR (its own tessdata) | works (text in the image's `title`) |
| Auto Image Occlusion | Image Occlusion editor, Auto-detect (Tesseract, tessdata extra files downloaded) | works (1 region) |
| AnkiMorphs + Japanese MeCab | Recalc | works (`am-not-ready` tags) |
| FrequencyMan | its AnkiMorphs and AJT MeCab tokenizers | works |
| KanjiVocab | its splitter | works (its `--node-format="…"` quotes reach mecab literally, desktop too) |
| MeCab UniDic | its MeCab process | works |
| Migaku Kanji GOD | start-up (downloads its 446 MB dictionary), reviewer, its MeCab parser | works |

Found and fixed: JavaScript `null` from `runJavaScript` came back as an
`NSNull` object instead of `None`, so JapaneseFurigana's selection check
(null when WebKit has no `ShadowRoot.getSelection`) crashed it
(docs/fixes.md, Add-ons).

Seen, not changed: Anki's editor script logs `TypeError: null is not an
object (evaluating 'e.anchor')` when a field takes focus in WebKit (its
selection save gets no selection from the shadow root); editing works.
Anki's editor saves every field about 600 ms after it shows a note; an
add-on that writes the same note within that time (a script running OCR
right after selecting it) gets overwritten, on desktop too.


## Menus over pages, first-run language list (2026-10-31)

Android emulator (Android 17, dark mode) and iPad Pro 11-inch (M4)
simulator (iOS 26.4).

| Test | Android | iPad sim |
| --- | --- | --- |
| First-run language list in dark mode, Qt's own palette (before a profile loads) | the selected row was blank (`#e4e5f0` on `#dae2ff`); after: black text | light mode: readable before and after |
| Anki's palette after a profile loads | highlight text stays white | — |
| Tools menu open, tap on the deck list page | the menu stayed open; after: it closes and the page's button under the tap does nothing; the next tap opens Create Deck | — |
| Review screen's More menu open, hit test where the card is | — | before: the WKWebView; after: Qt's view (taps can't be sent on the simulator) |
| Review screen's More (bottom right) tapped (Android: landscape, the button is hidden below 583 px) | before: menu at Qt's last tap; after: at the tap, (864, 359), the menu's right edge at the screen's | before: top left; after: above the button (a `pointerdown` and `click()` sent from the page) |
| Page tapped, then the menu bar's Edit | `QCursor.pos()` is Qt's again | — |

### Hardware keyboard on the review screen (2026-10-31)

iPad Pro 11-inch (M4) simulator. The simulator here has no window to type
into and synthetic HID events (`UIApplication _enqueueHIDEvent:`) didn't
arrive, so presses were stand-in `UIPress` objects handed to the same
methods UIKit calls; a tap on the card was `becomeFirstResponder` on the
WKWebView's content view.

| Test | Before | After |
| --- | --- | --- |
| No tap yet (Qt's view first responder), Space to Qt's view | card turns over | same |
| After a tap: Qt's focus window / active window | none / none | none until a key, then Qt's window |
| After a tap: Qt's key commands | 67, Space as `e`, Return as `n`, Enter as `r`; `I` and Space commands match nothing | none |
| After a tap: Space to WebKit's content view | (WebKit scrolls) | Qt's view first responder, card turns over |
| Then 3 to Qt's view | — | card graded, next card |

Not run: a real keyboard (needs an iPad with a keyboard, or the Mac's
keyboard on "My Mac (Designed for iPad)", started from Xcode), a key typed
into a page's text field (kept by WebKit, `isFocusingElement`).

Seen, not changed: Android has the same symptom with a different cause.
After a tap on the card, `adb shell input keyevent` Space and I reach no Qt
shortcut (the WebView keeps Android's key focus).

## Desktop image: Microsoft fonts download (2026-10-31)

Codespace (Ubuntu, curl 8.5). The script alone, with `HOME` in a scratch
folder, and the image built from `desktop/`.

| Test | Result |
| --- | --- |
| Fresh download from SourceForge | 31 files installed in 3 s; installers' folder removed |
| "Arial Greek" with and without the alias file | Arial / DejaVu Sans |
| Local server with 5 of 11 installers and one corrupt (`ANKI_MS_FONTS_URL`) | three rounds, then "couldn't download" the 6; the 5 good ones kept in `.cache/anki-ms-fonts` |
| Same server, now complete | fetched only the 6 missing ones (server log), installed |
| Container, `ANKI_MS_FONTS=true` | fonts after 10 s, `fc-match "Arial Greek"` → Arial as `abc`; no download after a restart |

Not run: the full `desktop/test/run.sh` (its two new checks were run by
hand in the container above).

## Hidden add-on pages: Contanki's white box (2026-11-17)

TestFlight feedback (0.2.8 build 215, iPad16,6, iPadOS 27.2.1): Contanki
left a white box over the top left. iOS Simulator (iPhone SE, Python
synced from the repo), Contanki's steps run with devcmd: `AnkiWebView(mw)`,
`setFixedSize(0, 0)`, `stdHtml(...)`.

| Test | Before | After |
| --- | --- | --- |
| View's geometry after `stdHtml` | 160×160 (native window 160×160, shown) | empty, native window hidden |
| Screen | white 160×160 pt box over the menu bar and deck list | no box |
| `runJavaScript` on the hidden page | — | runs (`1+window.ok` → 2) |
| `document.visibilityState`, `navigator.getGamepads` | — | `visible`, function |

Not run: Contanki itself with a real game controller (none here), Android.

## kioku:// links (2026-11-17, devices 2026-11-18)

TestFlight feedback asked for a URL scheme to add cards and sync. Host
tests: `shared/tests/test_urlscheme.py` (parsing, notes on a real
collection, refusals, media).

iOS Simulator (iPhone SE, 2026-11-17): the installed build with
`CFBundleURLTypes` added to its Info.plist and Python synced from the repo;
links opened with `xcrun simctl openurl` (iOS asks "Open in Kioku?") and in
the app with `QDesktopServices.openUrl`. A Simulator app started by the
system (not `simctl launch`) has no `USER`, and Anki's `getpass.getuser()`
fails before Kioku starts: `xcrun simctl spawn booted launchctl setenv USER
mobile` for cold-start tests.

iPhone 15 Pro Max (iOS 27, dev build from the repo) and Samsung M30s
(Android 11, dev build): links sent with `xcrun devicectl device process
launch --payload-url <link> io.ankidesk.kioku` (iPhone) and `adb shell am
start -a android.intent.action.VIEW -d <link>` (Android); results read with
devcmd. Tests used the deck "Kioku Link Test" and the tag `linktest`.

| Test | iPhone | Android |
| --- | --- | --- |
| addnote, Kioku open: `日本語 🍣 C++ & a=b #x`, `<br>`, tags | ✓ all kept | ✓ |
| no deck / note type / field, empty first field, duplicate, unknown action, `file:` x-success, other profile | ✓ the right warning, nothing added | ✓ |
| no `type`/`deck` | ✓ the Add screen's choice (current deck, last note type) | ✓ |
| `dupes=1`, Cloze | ✓ | ✓ |
| image link (https, Wikimedia), sound link (mp3 from the Mac) | ✓ downloaded, `<img>` / `[sound:]` | ✓ (offline: the warning "Couldn't download a file for the note: … Network is unreachable", nothing added) |
| download 404 | ✓ warning, nothing added | ✓ |
| Kioku in the background (Home; another app for 40–60 s) | ✓ | ✓ (after the fixes below) |
| Kioku not running: addnote, a refused link, search | ✓ | ✓ |
| a link before the first profile exists (first-run language list) | – | ✓ waits for the profile |
| with review, Browse, Add window or Preferences open | ✓ note added, review stays on its card, "Added to …" and warnings shown on top | ✓ |
| search, again with Browse open | ✓ Browse shows the new search | ✓ |
| sync, logged out | ✓ AnkiWeb login, as the Sync button | ✓ |
| x-success | ✓ Safari opened the page (seen in the Mac's server log) | ✓ Chrome opened |
| links tapped in a browser (test page on the Mac): add, image, sound, Cloze, x-success back to the browser | ✓ Safari (by the user) | ✓ Chrome: opens Kioku without asking; duplicate and unknown-deck warnings, search, sync too; Kioku stays out of Chrome's task |
| Android: started by a link, file picker open, Home, app icon (3×) | – | ✓ same process, picker still open |
| Android: started by a link, process killed in the background, reopened from Recents | – | ✓ Kioku restarts, the note isn't added again |

Found and fixed during the runs (details in fixes.md, "Runtime: platform"):
opening Browse from inside Qt's `QDesktopServices::openUrl` call crashed the
app (Simulator); on Android, links never arrived (Qt calls the handler on
Android's UI thread), links sent while Kioku was in the background were
dropped (`singleTop`), and after a link had started Kioku, tapping the app
icon could start a second activity and restart Kioku.

On the first link that downloads from the local network, iOS asks for Local
Network access; the download fails with "Couldn't download a file …" until
it is allowed, then works.

Not run: Shortcuts on the iPhone, Tasker or another automation app on
Android, iPad.

## TestFlight feedback round: crashes and the top bar (2026-11-18)

Feedback and crash reports from Xcode's Organizer (its local copy; the App
Store Connect API refused with "a required agreement is missing or has
expired"). Crash logs symbolicated with the 0.2.8 (215) archive's dSYM
(`ios/build/xcode-dist`).

iOS Simulator (iPhone SE, 375 pt), app built by `tools/run_sim.sh` with Qt
rebuilt from source with all `ios/patches/qios-*.patch`; device library
(`tools/build_qt_plugin.sh`) builds with no new warnings. Fake touches: a
rubicon `UITouch` subclass (`type` 2 = Pencil, `phase` settable) sent to the
main `QUIMetalView` with `touchesBegan:withEvent:`.

| Test | Result |
| --- | --- |
| `applicationSupportsShakeToEdit`, `QIOSViewController.editingInteractionConfiguration` after a cold start | False, 0 (none); set in `prepare()`, before the first web view (its hook is the first one registered) |
| Pencil touch begins, its end never sent, touch released by Python; then a second Pencil touch begins and ends | no crash; the second touch is taken (no "ignoring additional Pencil") |
| Same, first touch still active | Qt's "ignoring additional Pencil while first is still active", no crash |
| Qt text field focused, unfocused, input method reset; then the window's undo manager's undo and redo | no crash |
| Top bar with Russian labels (swapped in by script), 375 pt | two balanced rows (3 + 2), bar height follows; deck list fits, its options column scrolls sideways as before |
| Top bar in headless Chrome, 420/375/360 px: Russian, German, English, with and without an add-on button | nothing past the edges; English stays one row |
| Host tests (`shared/tests/run.sh`) | all pass |

Not run: a real Pencil (iPad), a real shake (the Simulator here has no
window), a text responder freed while Qt has no focus window (UIKit kept the
responder alive in every attempt, so `qios-undo-freed-responder.patch` is
tested only for doing no harm), Android.

Seen here: the Samsung M30s's WebView is Chrome 87 (never updated),
which has no CSS `:has()`; none of `PHONE_CSS`'s rules applied there (its
deck list ran off the right edge). Fixed below ("Deck list on WebViews
without `:has()`").

## Deck list on WebViews without `:has()` (2026-11-18)

`PHONE_CSS` rules come twice: with `:has()` and with classes that
`VIEWPORT` sets when the WebView has no `:has()`. New `webscripts.py` was
hot-loaded into the running app (exec into the module, deck list
refreshed). "Fallback" = the same file with `:has(` renamed to an unknown
pseudo-class, so only the class rules can apply (what Chrome 87 sees).
Measured in the page: window width, deck table left/right edge.

| Device | `:has()` rules | Fallback |
| --- | --- | --- |
| Samsung M30s, Android 11, WebView 87 (real, no `:has()`) | before: table 15–533 px in a page wider than the screen, Learn cut off, Due off screen | table fits, all columns on screen |
| Emulator API 33, WebView 109, 412 dp | 69–343 of 412 | same, `kioku-decks` set |
| Emulator at 720×1280 @ 320 dpi (360 dp) | 42–318 of 360 | same |
| iPad Pro 13-inch (M5) sim, iPadOS 26.4 | 257–775 of 1032 (wide layout, phone CSS off) | same |
| iPhone 17 Pro Max sim, iOS 26.4 | 81–359 of 440 | same |
| iPhone SE (3rd gen) sim "Kioku narrow" | 48–327 of 375 | same |
| Host tests | all pass, new `test_phone_css.py` | |

Emulator gotcha: with its default 2 GB, Kioku_API33 got Kioku killed by
the low-memory killer while the deck list loaded; a cold boot with
`-memory 4096` and swiftshader crashed Kioku at its first paint
(`QOpenGLProgramBinaryCache::save`, SIGSEGV), twice. A cold boot with
`-memory 4096 -gpu host` worked.

## iPad menu bar (iPadOS 26) (2026-11-18)

iOS Simulator, iPad Pro 13-inch (M5), iPadOS 26.4, and the narrow iPhone
simulator (iOS 26.4); the sim app from `tools/run_sim.sh` with the repo's
Python synced into it. No Simulator window here, so the menu bar was never
opened on screen: the built menus were read in the app through
`UIMainMenuSystem.sharedSystem._rootMenu` (private, test only; it runs the
build handler), and rows were run through `UIApplication`'s
`canPerformAction:withSender:`, `validateCommand:` and `kiokuMenuRow:` as
UIKit calls them.

| Test | Result |
| --- | --- |
| Main window, deck list | Kioku, File (Anki's), Edit (Anki's Undo, then the system's Cut/Copy/Paste…), View, Tools, Window, Help; no Format, no Find |
| Shortcuts | ⌘Z Undo, ⇧⌘P Switch Profile, ⌘P Preferences, F1 Guide, F11 Toggle Full Screen; Study Deck (/), Create Filtered Deck (F) without keys |
| Help › About Anki from the menu | About opens; while it's up, every row is disabled (`canPerformAction` NO, attribute disabled); after closing it, enabled again |
| Browse opened | its Edit, View, Notes, Cards, Go, Help in their order; no File; Find and Replace ⌥⌘F and Create Filtered Deck ⌘G (both the system's Find keys until its Find group was removed; with it, they were rows without keys). Closed → the main window's menus again |
| Reviewing | Edit shows Undo, Edit Current and More (flags submenu, bury, suspend, card info…), rebuilt for each card; More's rows have no keys (inert, as before) |
| More › Mark Note from the menu | note marked; Undo row retitled "Undo Update Tag" and enabled, Redo disabled; Undo from the menu unmarks it |
| iPhone simulator | no menu bar module installed |
| On screen (DeviceHub, by the user) | the system bar shows only on hover; with Anki's row hidden (first version) the menus were out of sight, so the row stays |
| iPadOS 27.0 simulator (iPad Pro 13-inch (M5), runtime 24A434, downloaded with `xcodebuild -downloadPlatform iOS`; the 27.1 runtime that was installed supports only "iPhone Duo"): user turned "Automatically Show and Hide Menu Bar" off, the bar stayed on screen | key window safe area top 32, status bar frame height 32, Qt safe area 32 in both states; preference files: no menu bar key (only the multitasking mode, `SBChamoisWindowingEnabled`); app-side classes: only `SBSMenuBarSystemService toggleMenuBarVisibility`/`isMenuBarSupported` → not detectable |
| View › Show Menu Row run from the iPad's menu bar | row height 0, check mark off in the iPad's View menu, `kioku_menu_row` False; after relaunch still hidden; full screen on and off (`fullscreen._exit`): still hidden; Browse: its row hidden too |
| View › Toggle Full Screen from the iPad's menu bar (iPadOS 27 sim, by the user) | first: Anki's error dialog, `'NoneType' object has no attribute 'setWindowState'` (`app.activeWindow()` None); fixed in `fullscreen.toggle_with_guide` |
| Two full screen items (the iPad's Window › Full Screen resizes the window, Anki's only hides its bars) → Anki's renamed on the iPad | `actionFullScreen` text: Hide Toolbars → (toggle) Show Toolbars → (toggle) Hide Toolbars; enter then `fullscreen._exit` (swipe) → Hide Toolbars; the iPad's View menu shows "Hide Toolbars" with F11; no tracebacks |
| Swipe right on the iPad (user: shows the window list) → swipe off there | pages without the swipe script, `kioku:swipe-right` ignored; tooltip points to View › Show Toolbars |
| Host tests (`shared/tests/run.sh`) | all pass, with new tests for the shortcut → key command mapping and full screen without an active window |

Not run: opening the menu bar on screen and using it with touch or a
pointer, hardware keyboard shortcuts through the key commands (⌘Z, ⌘P), the
iPad app on a Mac, a real iPad, iPadOS 18 (the module only checks that
`UIMainMenuSystem` is missing there).

## Editor formatting on iOS (issue #17) (2026-11-18)

iOS Simulator, iPad Pro 13-inch (M5), iPadOS 27.0 (sim app with the repo's
Python synced in); Android emulator, Android 13, WebView Chrome 109. Before
the fix (sim, the same test page actions):

| Action on "hello" selected in a field | Before (iOS) | After (iOS) | Android |
| --- | --- | --- | --- |
| `getRangeAt(0)` | `DIV/0–DIV/0` (field's host, collapsed) | `#text/0–#text/5` | (uses the shadow root's selection) |
| Bold, italic, underline, superscript, subscript | unchanged | `<b>hello</b> world` …, selection kept; pressed again: removed | works |
| Text colour, highlight | unchanged | `<span style="color: …">hello</span>` / `background-color` | works |
| Remove formatting on `<b>hello</b>` | unchanged | `hello world` | works |
| Equations › MathJax inline | MathJax inserted empty, the text lost | `data-mathjax="hello"` | works |
| Cloze (Cloze note) | — | `{{c1::hello}} world` | works |
| Underline at the caret, then typing (iOS: real keyboard input through `WKContentView insertText:`) | typed text not underlined | `hello world<u>XY</u>` | works |
| Backward selection (anchor after focus) | — | `anchorOffset` 5, `focusOffset` 0, underline applied | — |
| Caret restore when a field gets the focus without a tap | caret at the end | caret at the end: WebKit empties the selection before `blur` (`rangeCount` 0), so Anki saves nothing; a tap places the caret itself (fixed later the same day, below) | — |

New in-app test `editor-formatting` (above): passes on the iOS simulator and
the Android emulator; fails on the simulator without the fix (`b: field is
'hello world'`). Android needed two test-only measures: a WebView that was
never tapped has no focus, and a field's `focus()` then fires no focus
events (the toolbar stays disabled), so the test sends them; Blink's
`execCommand('insertText')` fires no `beforeinput`, so the keystroke is a
`beforeinput` event. Full simulator suite and crash sweep: 49 passed. Host
tests: 174 passed, with node tests for the script on a WebKit-like page and
for it staying off where shadow roots have `getSelection`.

Not run: a real iPhone or iPad (taps on the toolbar), the web version in
Safari, iOS 17/18 (`getComposedRanges` takes shadow roots as arguments
there; the script tries that form when the options form throws).

### Caret restore (2026-11-18, later)

Same simulator and emulator. The new in-app test `editor-caret` puts the
caret at offset 3 of "hello world", moves the focus to the next field and
back with `focus()` (no tap), and reads the caret; then the same with a
backward selection (8 → 2).

| | Before (iOS) | After (iOS) | Android |
| --- | --- | --- | --- |
| Caret after the field gets the focus back | end of the field (`ANKI-EDITABLE`/1) | `#text`/3 | `#text`/3 |
| Backward selection | — | "llo wo", focus at 2 | "llo wo", focus at 2 |

Android needed the field's blur sent before `focus()` on the next field:
Blink moves the selection to the next field with `focus()`, and a blur sent
after that saved the wrong place (a real blur comes first).

`editor-formatting` took 56 s on an emulator slowed by a busy host (load
average 7): it now has a 90 s budget (a test function's `timeout`), the
others keep 45 s. Results: simulator full suite and crash sweep 50 passed;
emulator 49 passed, 1 failed: `browse` took longer than 45 s, also with
the suite from before this change (57 s after an editor test, 10 s on its
own). Host tests: 175 passed (node test for the selection reported during a
field's blur, and not after its `focusout` or for another element).

Not run: Tab with a hardware keyboard on a real iPad, returning from a
dialog or the HTML editor (the same blur and focus without a tap).

## Gamepads and controllers (issue #18) (2026-11-18)

New: `kioku/gamepad.py` (buttons → actions), iOS
`kioku_platform/gamepad.py` (GameController framework), Android
`KiokuGamepad.java` (key and motion events of gamepad sources, taken in
`KiokuActivity.dispatchKeyEvent` / `dispatchGenericMotionEvent`).

Host tests: `test_gamepad.py` (9: settings round trip, review buttons, deck
list and overview, the same button from two sources, triggers and sticks,
repeat only for moves, off, keyboard shortcut run in the window, dialog
Tab/press/close, Buttons dialog); all 186 passed.

iOS Simulator (iPhone 17 Pro Max, repo Python synced in). The simulator
lists an MFi "Gamepad" controller; a live controller ignores `setValue:`,
so the handler block Kioku installs was called with a `capture()` snapshot
whose values were set:

| Input (snapshot) | Reported |
| --- | --- |
| d-pad `setValueForXAxis:0 yAxis:-1` | Down pressed, the others up |
| button A 1.0 | A pressed |
| right stick y −0.8 | `right` 0, +0.8 (y flipped to "down is positive") |
| left trigger 0.9 | `triggers` 0.9, 0 |

Actions through the listener on the real app: Down highlights the deck
(outline in Anki's focus colour), A opens it, A Study Now, A shows the
answer, A answers Good, View back to the overview, B back to the deck
list. Preferences › Advanced shows the Gamepad group ("Connected:
Gamepad"); Buttons… opens; R1 moved the focus to a combo box; B closed the
Buttons dialog, then Preferences. No errors in kioku.log.

### Controls like AnkiDroid's (2026-11-18, later)

Settings are per action (AnkiDroid's Settings › Controls), version 2 in
`pm.meta["kioku_gamepad"]`: `{"version": 2, "enabled", "review": {action:
["A@answer", …]}, "other": {…}}`. Press-to-bind (`ButtonPicker`: the
next press goes to the dialog, not to an action), card side per binding,
"now used for …; OK moves it here". Actions run Anki's own shortcuts
(Space only on the question side; answer keys from `pm.get_answer_key`;
R, M, E, *, -, =, @, !, Ctrl+1–4, I, O, V, Shift+V, 5; D, S, A, B, Y);
Back, Undo and the scrolls call `moveToState`/`undo`/page JS.

Host tests: `test_gamepad.py` (13, against a window with real QShortcuts
like Anki's) and `test_gamepad_anki.py` (4): Anki 26.09.4's
`Reviewer._shortcutKeys` and `AnkiQt.setupKeys` run with stand-ins, and
every key Kioku uses must reach the expected method; `onStudyKey` on the
overview studies; the deck rows Anki renders have the `tr.deck`/id,
`.current`, `a.collapse` "+" and `a.deck` the highlight reads. All 194
passed. **After an Anki update**, a failure here means kioku/gamepad.py
needs a look.

Samsung M30s (Android 11), dev build with `gamepad.test`:
`apptest.py android --only gamepad,gamepad-native`: 6 passed (version,
setup, add, gamepad, gamepad-native, cleanup). Through Android's own input
pipeline (`adb shell input gamepad keyevent`): DPAD_DOWN highlighted a deck,
a keyboard's DPAD_DOWN (`input keyevent`) didn't move it, BUTTON_A opened
the deck, BUTTON_B went back. Controls dialog: list of actions with their
buttons; Add Button… took a BUTTON_A / BUTTON_Y key event and said "Now
used for “Good”" / "“Easy”". Fixed from the screenshots: PlayStation's
✕ ○ □ △ were empty boxes in Android's font (now words), and the pressed
button's large label stayed small (Android fonts have a pixel size).

iPhone 15 Pro Max (iOS 27), dev build: `apptest.py ios --only
gamepad,gamepad-native`: 6 passed; `gamepad-native` connected Apple's
virtual controller ("Apple Touch Controller", its on-screen buttons
shown) and pressed A with `setValue:forButtonElement:`, through
GameController and Kioku's handler. Controls dialog (dark mode) with the
virtual controller connected: Add Button… took a virtual Y press, "Now
used for “Easy”"; Cancel left the settings unchanged; after disconnect
no controller and no capture left.

Not run: a real controller (none here). (Earlier, on the 2 GB emulator, Android's
low-memory killer ended Kioku, ~1.2 GB PSS at idle, before any gamepad
input.)

## Missing pictures after a sync with AnkiWeb, iOS (2026-11-19)

Reported by many iPhone users (image occlusion too); the reporter's
screenshot showed Sync still spinning. Setup: a local `anki.syncserver`
on the Mac with a test collection (75 media cases: every image format,
names with spaces, NFC/NFD, CJK, Arabic, emoji, `# % & + ' ( ) ; , @ = $`,
a 180-character name, case and normalisation mismatches, 10 image
occlusion cards; plus 300 incompressible 200 KB files and a 36 MB
picture), reached through a proxy limited to 300 KB/s. iOS Simulator
(iPhone 17 Pro Max, iOS 27) and the iPhone 15 Pro Max (dev build with the
fix hot-loaded, over Wi-Fi).

| Test | Before the fix | With the fix |
| --- | --- | --- |
| Download, app kept open: files on disk | 347/347, same SHA-1 as the server | 347/347, same SHA-1 |
| Every test card's answer in the reviewer (`naturalWidth` of each `<img>`) | 76/80; failing: `.jp2` (WebKit has no JPEG 2000, nor has Chromium), raw `%20` in `src`, `LOWER_CASE.PNG` for `lower_case.png` (case-sensitive file system), a double-escaped test name | not repeated (rendering untouched) |
| Image occlusion cards | 10/10 draw (canvas + picture) | not repeated |
| Leave for 60 s, connection kept | suspended within 5 s, resumes on return | download goes on ~27 s in the background (background task), then suspended; expiry handled |
| Leave, connection drops, back after 70 s | **"Connection timed out" / raw `HttpError { code: 303 … }`, media sync stops at 72/347**, nothing retries | retry queued, resumes on return, 347/347, same SHA-1, no message |
| iPhone: same, over Wi-Fi | not run | download continued in the background until the drop, resumed on return, 347/347 |
| Kioku killed during the download, opened again | auto sync resumes it | not repeated |
| Screen lock during a sync (idle timer off beforehand, as in release builds) | locks | stays on while syncing, back to locking after |
| Sync button while downloading | spinner only | `↓N` badge (top right of Sync, inside the bar) |

Host tests: `shared/tests/run.sh`, all passed, 13 new in
`test_ankiwebsync.py` (retries, quiet start, completion, return to the
foreground, error handling and text, badge count).

### Full round on the iPhone, dev build with the fix (2026-11-19)

iPhone 15 Pro Max (iOS 27), dev build installed with
`ios/tools/run_device.sh` (no hot-loading), fresh profiles
MediaTestPhone2/3 against the local server over Wi-Fi (300 KB/s, then
100 KB/s).

| Test | Result |
| --- | --- |
| `apptest.py ios` (in-app suite + crash sweep), first build and final build | 52 passed, 0 failed, 1 skipped (programs: none on iOS); 22/22 sweep steps, both times |
| Screen lock during a sync (idle timer off beforehand, as in release builds) | off while syncing; afterwards the phone locked by itself again |
| Leave for 60 s, connection kept | 33 → 98 files while away; task ran out after ~27 s and ended cleanly; continued on return |
| Leave, connection drops (`NetworkError` "Connection timed out" this time) | no message; resumed on return 2 s later |
| Kioku killed during the download, opened again | resumed by the sync on open |
| All 347 files after the download | same SHA-1 as the server |
| Every test card's answer in the reviewer | 76/80, the same 4 as on the simulator (none Kioku's); 10/10 image occlusion cards drawn |
| Check Media | 20 "missing": the test's `%`-encoded links (`with%20space.png`…; Anki's check doesn't decode them, the reviewer does) and `LOWER_CASE.PNG` |
| Leave twice in one sync, the first time until the task ran out | **bug, fixed**: the second trip got no background time. Now a new task starts on return: 111 → 150 files during the second trip |
| Connection gone while Kioku stays open | **bug, fixed**: after the last retry nothing was shown (the retries run as periodic syncs, whose errors Anki keeps quiet). Now: retries at 5 s, 30 s, 2 min, then "A network error occurred. … Some pictures and sounds are not downloaded yet. Kioku continues when you come back to it, or tap Sync." (2.8 min after the drop) |
| Then connection back, leave and return | resumed, 347/347 |

Not run: real AnkiWeb (the test account has no big media), a release
(TestFlight) build, the Android emulator (the shared retry code is new
there too; Android already kept the network through its service).

## AnkiConnect with Kioku in the background, iOS (issue #21) (2026-11-19)

iPhone 15 Pro Max (iOS 27), dev build installed with
`ios/tools/run_device.sh`, profile User 1 with AnkiConnect (2055492159)
listening on 127.0.0.1:8765. Safari as the client app
(`devicectl device process launch --payload-url http://127.0.0.1:8765
com.apple.mobilesafari`, which also sends Kioku to the background), whole
screen captured with `devicectl device capture screenshot`.

| Test | Result |
| --- | --- |
| Without the option (earlier the same day) | Kioku suspended about 5 s after leaving; requests hang until it's opened again |
| Preferences › Advanced › Background, option ticked | status "On: Kioku keeps running in the background"; the setting saved in the profile list |
| Built app's Info.plist | `UIBackgroundModes` = `location`, `NSLocationWhenInUseUsageDescription` present |
| Kioku in the background, Safari asks right away | `{"apiVersion": "AnkiConnect v.6"}`; location arrow in the Dynamic Island |
| Kioku in the background for 7 min, Safari asks again (new URL, not cached) | `{"apiVersion": "AnkiConnect v.6"}`; location arrow still shown |

Host tests: `shared/tests/run.sh`, 210 passed; new: the Advanced group
(only where the platform has it, saved and applied, status texts), the
Info.plist keys, and `kioku_platform/location.py` with a stand-in
`CLLocationManager` (asks for access, then starts; stops when turned off;
access denied).

Not run: the screen locked, longer than 7 minutes, battery use, iPad,
the location alert itself (access was already granted on this phone), a
TestFlight build and App Review.

### Protecting the location from add-ons and pages (2026-11-19, later)

Same iPhone, new dev build with the location guard and
`NSLocationDefaultAccuracyReduced`; then Precise Location turned off for
Kioku in the Settings app (as new installs get it by default).

| Test | Result |
| --- | --- |
| Start-up | "location guard installed" logged before add-ons load; Kioku's own manager started, option "on" |
| Stand-in add-on (devcmd): its own `CLLocationManager`, best accuracy, own delegate; `requestWhenInUseAuthorization`, `requestAlwaysAuthorization`, `startUpdatingLocation`, `requestLocation`, `startMonitoringSignificantLocationChanges` | all blocked (logged once each); `location` nil on its manager and on Kioku's; no locations or errors delivered in 20 s |
| Same add-on sets its delegate on Kioku's manager | refused; Kioku's delegate kept; option still "on" |
| Card page: `navigator.geolocation.getCurrentPosition` (high accuracy, 15 s timeout) | no position after 20 s, no iOS or WebKit prompt (WebKit's location goes through the guarded `CLLocationManager`) |
| `accuracyAuthorization` with Precise off | 1 (reduced) |
| Approximate location: Kioku in the background 7 min, Safari asks AnkiConnect | `{"apiVersion": "AnkiConnect v.6"}`; the location arrow showed at first, not after 7 min |
| Heartbeat thread in Kioku (a timestamp every 10 s), Kioku in the background 415 s, nothing asking it anything | 42 beats, largest gap 11 s: Kioku ran the whole time. The screen locked by itself during the run (screenshot black): it keeps running with the screen locked too |

Host tests: `shared/tests/run.sh`, all passed; new: the guard's rules
(only Kioku's manager, only with Kioku's delegate, temporary full accuracy
never), the warning before the option turns on, the "take it back in
Settings" status, the Info.plist key.

Not run: an add-on written to undo the guard (it can: same process;
documented), battery use, iPad, longer than 7 minutes, App Review.

## Anki's Python and Qt: AnkiHub on iOS and Android (2026-11-20)

TestFlight feedback (iPhone18,2, iOS 27.2.1, 26.09.4 build): "Add-on Startup
Failed: AnkiHub", `UnserializableField: Field "tags" of type
Optional[List[str]] in NoteInfo is not serializable`. Reproduced on the Mac
with Python 3.14 and AnkiHub's bundled mashumaro 3.15; Python 3.13 (Anki
26.09.4's) loads it. Fix: Kioku runs the versions Anki pins
([fixes.md](fixes.md#anki-updates)).

| Test | Result |
| --- | --- |
| Host tests on Python 3.13 with `aqt[qt]` (PyQt6 6.11.0, Qt 6.11.2): 219, incl. `test_anki_pins.py` | ✅ |
| iOS Simulator (iPhone 17 Pro Max): in-app suite + crash sweep, `version` = Anki 26.09.4, Qt 6.11.2, PyQt 6.11.0, Python 3.13.18 | ✅ 55/55 |
| The `version` test catches a stale build: the first Simulator build still linked Qt 6.11.0 (cached toolchain) | ✅ failed, then fixed (`cmake_fresh.sh`) |
| iPhone 15 Pro Max, iOS 27: in-app suite + crash sweep | ✅ 54 passed, `programs` skipped as before |
| AnkiHub 2026-11-18.1 installed from AnkiWeb in the app (Simulator and iPhone): loads (136 modules), shows "Sign in to AnkiHub", `NoteInfo.from_dict`/`to_dict` round trip, no startup failure | ✅ (removed again from the iPhone afterwards) |
| Objects freed on the main thread (the 3.14 stack-bounds trashcan leak): 300 of 300, Simulator and iPhone | ✅ |
| Android emulator (Kioku_API33, SwiftShader): in-app suite + crash sweep, `version` = Anki 26.09.4, Qt 6.11.2, PyQt 6.11.0, Python 3.13.18 (built from source) | ✅ 53 passed, `numpad-done` and `microphone` skipped |
| AnkiHub 2026-11-18.1 installed from AnkiWeb in the app (Android emulator): loads after a restart (120 modules), `NoteInfo` round trip, no startup failure | ✅ |
