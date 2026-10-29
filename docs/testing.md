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
(`qios-null-focus-object.patch`). iPhone 15 Pro Max, iOS 27.0.1, dev builds.

| Test | Result |
| --- | --- |
| Report symbolicated with the archive's binary (same UUID `6F3F22D9…`) | `querySelection()` + 68 ← `-[QIOSSelectionRecognizer acceptTouchesBegan:]` ← `-[QIOSLoupeRecognizer touchesBegan:withEvent:]`; the fault is `ldr x8, [x0, #0x8]` in `QCoreApplication::sendEvent` with `x0` = `focusObject()` = null |
| Looking for the trigger: a focused line edit's dialog closed with `deleteLater`, `sip.delete`, hide and delete together, `setWindowFlags`, `windowHandle().destroy()`; `aqt.utils.getText`; Add › Deck (Study Deck) picked; Browse search then Back; Preferences spin box then close; the editor's web view made first responder | ✅ every time the recognizers went away with the focus (checked through UIKit's `gestureRecognizers`, sampled 0-1000 ms after the change) |
| A minute of real taps (Browse search, editor fields, keyboard swiped down, Study Deck filter, text boxes then the deck list) with a monitor for "focus object null while Qt's recognizers are attached" | ✅ no such state, no crash; two changes to a null focus, both signalled |
| Forced: a text field focused, then `QGuiApplicationPrivate::focus_window` set to null in memory (what `QWindowPrivate::destroy()` does), one tap, unpatched build | ❌ crash, `Kioku-2026-10-25-121855.ips`: the reported stack (`querySelection()` ← `-[QIOSCursorRecognizer acceptTouchesBegan:]`) |
| Same with the patched `libqios.a` (the app's `querySelection` now starts with `cbz` on `focusObject()`) | ✅ several taps on the deck list, the dialog's text box and buttons; app kept running, no new crash report |

Not found: which path in the tester's app left the focus null without the
signal. The patch covers every such path for this crash.

Which AnkiWeb add-ons need libraries or programs Kioku doesn't bundle: [addon-deps.md](addon-deps.md).
