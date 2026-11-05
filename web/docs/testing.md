# Testing

## How

- **Core without Qt (node, seconds):** `tools/link_core.sh` links CPython
  and rsbridge into `build/core/core.mjs`; run a script from
  `tools/core/` with `node tools/core/run.mjs /app/core_probe.py` from
  `build/core/` (copy `tools/core/run.mjs` there first). Good for Rust or
  Python core problems: the full app takes ~5 minutes to relink.
- **Smoke test:** `python3 tools/test/smoke.py [deck.apkg]` (server on
  8765): ~4 minutes, prints PASS/FAIL per check. Run it after changes.
- **Safari, iOS Safari (no WebDriver):** `python3 tools/test/selftest.py
  safari|ios|chrome [deck.apkg]` runs the smoke test inside the page:
  `tools/serve.py` (with `KIOKU_SELFTEST`) adds `tools/test/selftest.js` to
  `app.html` on a fresh port (fresh storage), the page runs the steps and
  posts its console back. Steps find buttons and fields by selector, so any
  window size works. `safari` opens a tab in Safari, `ios` boots an iPhone
  simulator (`IOS_DEVICE=<name or UDID>`) and screenshots the `shot` steps,
  `chrome` (headless) checks the self-test against `smoke.py`.
  `ONLY=cross` runs only the cross-origin check.
- **The app (headless Chrome):** `python3 tools/serve.py build/cmake 8765`,
  then `cd tools/test && npm install` once and
  `node boot.mjs '<steps>'` (steps documented at the top of `boot.mjs`). Each
  run starts a fresh profile unless `PROFILE=<folder>` keeps Chrome's data
  (IndexedDB) between runs (then `NOFIRSTRUN=1`); downloads land in the
  current folder, gets through the
  language dialogs and runs the steps. Screenshots land in the current
  folder. The coordinates below are for the 1000×700 viewport.
  `URL=<app page>` tests another server, e.g.
  `URL=http://localhost:8765/app.html` or the Worker under `wrangler dev`
  (`URL=http://127.0.0.1:8787/app.html`).
- **Inside the app:** the `devexec` hook (`["py", "…"]` in `boot.mjs`, or
  `__kiokuWeb.post({type: "devexec", code})` in the console) runs Python
  and prints `result`. `["pause"]` prints the main thread's stack when the
  page hangs (needs `--profiling-funcs`, on by default).

Useful step sequences (after the deck list is up, ~9 s):

```
add a note:   ["click",428,37,7000],["click",500,173,800],["type","Front"],["click",500,249,800],["type","Back"],["click",761,674,3000],["click",948,674,5000]
study:        ["click",307,167,4000],["click",603,168,5000],["click",500,300,500],["key","Space",3000],["key","3",3000]
import:       ["upload","/path/deck.apkg",[614,666],8000],["click",943,66,8000],["click",48,21,5000]
browse/stats: ["click",500,37,8000] / ["click",575,37,10000]
```

## Results

### 2026-10-23: feasibility (node 26 and Chrome 155, headless, macOS)

| Test | Result |
| --- | --- |
| node: create a collection, add 200 notes, answer a card, search from a worker thread, stats report | ✅ 1.3 s |
| node: update check through reqwest (tokio runtime) | ✅ clean `NetworkError` (no relay) after the mio pipe fix; panicked before |
| Chrome: Python + rsbridge, collection created and a card rendered in the page | ✅ |
| Chrome: PyQt6 widgets; clicks reach Python slots after `app.exec()` | ✅ |
| Chrome: nested `QMessageBox.exec()` returns Yes (Asyncify) | ✅ |
| Chrome: collection opened on a `ThreadPoolExecutor` thread, result on the GUI thread | ✅ |
| Chrome: unmodified aqt: language dialogs, profile, main window, menus, Tools › Check Database | ✅ |

### 2026-10-24: Anki's pages (Chrome 155, headless, 1000×700)

| Test | Result |
| --- | --- |
| Deck list, toolbar, bottom bar render | ✅ |
| Add: editor renders, typed note saved with both fields; deck list shows New 1 after closing | ✅ (after the eval-order and removeChild fixes) |
| Deck overview, Study Now, question → Space → answer with buttons → 3 (Good) | ✅ card moves to learning |
| Import File: browser picker → import page (SvelteKit) → Import → "20 new notes imported" → deck list shows AMBOSS Test 20 new | ✅ (`AMBOSS Test.apkg` from Kioku's `build-testdata/amboss`) |
| Browse window opens (sidebar, table) | ✅ |
| Stats (graphs page) | ✅ |
| Update check | ✅ fails cleanly ("update check failed: A network error occurred") |
| Export download | ✅ see 2026-10-24 b |
| Reload keeps the collection | ✅ see 2026-10-24 b |
| Audio, TTS | ✅ see 2026-10-24 b; sync ❌ not implemented |

### 2026-10-24 b: storage, audio, TTS, export (Chrome 155, headless, test-deck/)

Run with `PROFILE=<folder>` so IndexedDB survives between runs.

| Test | Result |
| --- | --- |
| Import `Anki xiehanzi - HSK 1.apkg` (24 MB, 311 media files) | ✅ 602 notes, 4 decks, 311 media files |
| Reviewer: question audio (`[sound:cmn-的.mp3]`) | ✅ `WebAudioPlayer` → `<audio>` with a blob URL, playing |
| `{{tts}}` (`TTSTag` zh_CN) | ✅ `WebSpeechPlayer` picks a zh_CN voice (macOS voices through Chrome) |
| Export .apkg with media (`save_path` + `export_anki_package`) | ✅ `HSK.apkg` downloaded, 24.4 MB |
| Reload (same browser profile, no first-run dialogs) | ✅ profile "User 1", 602 notes, 311 media files, audio plays from the saved media |
| Import `Anki-NeetCode-Pro.apkg`, review | ✅ card renders; `CodeMirror is not defined` once (the deck's scripts, timing; not on the next run) |
| HSK 1 Writing cards: Space/3 after the question | ⚠️ not answered: the template's drawing canvas keeps the keys |
| Export through File › Export dialog clicks | ⏳ not clicked through (the same `save_path`) |

### 2026-10-24 c: sync (Chrome 155, headless)

Local server: Anki's `anki-sync-server` built from Kioku's Anki source
(`PROTOC=$(command -v protoc) CARGO_TARGET_DIR=…/build/host-sync cargo build
--release -p anki-sync-server` in `ios/deps/anki`), run with
`SYNC_USER1=kioku:test SYNC_HOST=127.0.0.1 SYNC_PORT=8090`, and
`KIOKU_RELAY_ALLOW=127.0.0.1:8090 python3 tools/serve.py build/cmake 8765`.

| Test | Result |
| --- | --- |
| Login with a wrong password (AnkiWeb) | ✅ "Email or password was incorrect" (TLS through the relay) |
| Local server: login, Sync button, "Replace it with local collection?" → Yes | ✅ full upload + media (322 files, 70 MB on the server) |
| Local server, fresh browser profile: Sync → "Download?" → Yes | ✅ 752 notes, 322 media files |
| AnkiWeb (test account, fresh profile): `sync_collection` → full sync required → `full_download` | ✅ 20,858 notes, 39,754 cards, 9 decks, ~3 s; never uploaded |
| `full_download` without a normal sync first | ⚠️ AnkiWeb 400 "missing original size" (skips `meta`, which picks the endpoint; Anki's UI never does this) |
| Firefox, Safari, a phone browser | Safari and iOS Safari: see 2026-10-26; Firefox ⏳ not tested |

### 2026-10-24 d: add-ons (Chrome 155, headless)

The 14 add-ons from Kioku's iOS/Android tests, downloaded on the host
(`https://ankiweb.net/shared/download/<id>?v=2.1&p=260903`), written into
the wasm file system and installed with `addonManager.install(path,
manifest=dict(package=<id>, …))` as Get Add-ons does (folder = AnkiWeb id;
HyperTTS finds its config only that way). Error dialogs at start dismissed
with Enter.

| Add-on | Code | Result |
| --- | --- | --- |
| Speed Focus Mode | 1046608507 | loads |
| Color Confirmation | 1084228676 | loads |
| HyperTTS | 111623432 | loads (after `_ssl`); panel on the deck list; Configure Services window opens; HyperTTS menu in Browse |
| Review Heatmap | 1771074083 | loads; heatmap section on the deck list ("No activity data" without reviews) |
| Fill the blanks | 1933645497 | loads |
| AnkiConnect | 2055492159 | loads; its server can't start (`socket` has no `SO_REUSEADDR`; a page can't accept connections): expected, its error dialog holds up add-on loading until closed |
| Customize Keyboard Shortcuts | 24411424 | loads (deprecation warnings) |
| AnkiWebView Inspector | 31746032 | loads (needs Qt WebEngine dev tools: the browser's own dev tools instead) |
| Edit Field During Review Cloze | 385888438 | loads |
| Colorful Tags | 594329229 | loads |
| True Retention | 613684242 | loads |
| Anki Simulator | 817108664 | loads |
| Advanced Browser | 874215009 | loads; Browse opens |
| AnKing Notetypes | 952691989 | loads; AnKing menu |

| Test | Result |
| --- | --- |
| Install from .ankiaddon (jsonschema manifest check) | ✅ after building rpds-py for wasm |
| Python HTTPS (`requests.get` ankiweb.net through the relay) | ✅ 200 (after `_ssl`, the socket option and `poll()` fixes) |
| Tools › Add-ons › Get Add-ons code path (`download_addons`, Review Heatmap 1771074083) | ✅ downloaded and installed from AnkiWeb |
| Add-ons still there after a reload | ✅ (`addons21` is under the saved folder) |

### 2026-10-24 e: AMBOSS add-on (1044112126)

| Test | Result |
| --- | --- |
| Get Add-ons, code 1044112126 | ✅ installed from AnkiWeb |
| Loads; talks to `anki.us.production.amboss.com` through the relay | ✅ (after the relay change) |
| Onboarding / login dialog | ✅ renders (after the localhost and COEP fixes) |
| `ambossAddon is not defined` once at start | ⚠️ its inline script is in `web_content.head`, before its own scripts; same order on the desktop |
| Log in through its form (test account from Kioku's `.env`) | ✅ logged in; its "Mobile Support" intro follows (after the main-thread `poll()` fix) |
| After a reload: still logged in; AMBOSS menu, toolbar button, Qbank widget on the deck list | ✅ |
| Kioku's "AMBOSS Test" deck: terms underlined while reviewing | ✅ |
| Hover a term (ADPKD): pop-up with title, images, text | ✅ (a click closes it again: tippy's toggle); the pop-up is taller than the reviewer and is cut at its bottom |
| Qbank session | ⏳ not tried |

### 2026-10-24 f: smoke test (`python3 tools/test/smoke.py`, Chrome 155, headless)

Three runs in one fresh browser profile (about 4 minutes): first run,
reload, extra windows. 27/27 passed, no page errors.

| Check | Result |
| --- | --- |
| First-run dialogs → profile and collection | ✅ |
| Add a note through the editor; answer it in the reviewer | ✅ |
| Import HSK 1 (.apkg, 311 media files); its audio plays; `{{tts}}` speaks | ✅ |
| Browse, Stats, Deck Options, Preferences, Card Types open | ✅ |
| Check Database; undo status | ✅ |
| Export .apkg with media → download (24 MB); export .colpkg | ✅ |
| Reload: profile, notes, review, media kept | ✅ |
| Filtered deck, Custom Study, Note Types, Empty Cards, Check Media, Find and Replace, CSV import page | ✅ open |
| Dark theme; "follow system" follows the browser's `prefers-color-scheme` | ✅ (was hard-coded light) |
| Switch profile (profile manager) | ✅ |

The window checks only see that the window opens, not that everything in
it works.

### 2026-10-24 g: any origin, Cloudflare Worker (Chrome 155, headless)

The page's origin instead of a hard-wired `127.0.0.1`; `tools/dist.sh`
and `cloudflare/` with `wrangler dev` (wrangler 4.148.0), then deployed.

| Test | Result |
| --- | --- |
| Smoke test, `serve.py` at `http://127.0.0.1:8765` | ✅ 27/27 |
| Smoke test, `serve.py` at `http://localhost:8765` (failed before) | ✅ 27/27 |
| Smoke test, Worker at `http://127.0.0.1:8787` (compressed wasm and data) | ✅ 27/27 |
| Worker relay: `requests` to AnkiWeb; to example.com (not in `RELAY_ALLOW`) | ✅ 200; ✅ 403 |
| Worker relay: 23.6 MB over HTTPS (python.org) | ✅ 12.0 s (serve.py: 10.2 s) |
| Deployed (`https://kioku.krmanik.workers.dev`, free plan): smoke test | ✅ 27/27; wasm sent as brotli (17 MB) |
| Deployed: relay to AnkiWeb; example.com refused | ✅ 200; ✅ refused |
| Deployed: free plan's 10 ms CPU limit with a long sync | ⏳ not tested |
| Sync through the Worker relay | ⏳ only AnkiWeb requests (above); no full sync yet |

### 2026-10-24 h: fonts, time zone, storage size (Chrome 155, headless, macOS)

| Test | Result |
| --- | --- |
| First-run language list: Chinese, Japanese, Korean, Thai, Oriya | ✅ rendered (were boxes) |
| Browse with the HSK deck: hanzi in Sort Field | ✅ rendered |
| HSK deck's Created column shows 1970-01-01 | ✅ correct: the deck's note ids are 1–602 (made by a script, not Anki); the same on the desktop |
| Note added in the app at 12:12 IST: Created column | ✅ 12:12 (was 06:34, UTC) |
| Chrome in America/New_York at 02:42 EDT: Created; `sched.day_cutoff` | ✅ 02:42; ✅ today 04:00 EDT |
| 1 GB of files (random) in `/home/web_user`, saved, reload | ✅ all back; written 9.5 s; start ~10 s slower; JS heap ~1.1 GB |
| 3 GB of files, saved, reload | ✅ all back; written 28.5 s; JS heap ~3.1 GB; quota reported 11–13 GB |
| Notice on opening; `navigator.storage.persist()` after OK | ✅ shown; ✅ asked (headless: not granted) |

### 2026-10-24 i: download progress (Chrome, headless, macOS)

| Test | Result |
| --- | --- |
| Worker at `http://127.0.0.1:8787`, network throttled to 4 MB/s: loading screen | ✅ bar and "Downloading Kioku… N%", 2% → 96% in ~11 s, then "Starting Kioku…" |
| Same, notice open | ✅ "Downloading… N%" next to OK |
| After the download | ✅ first-run language list |

### 2026-10-24 j: Onigiri add-on (1011095603, 2.0.2-Bento; Chrome, headless, macOS)

| Test | Result |
| --- | --- |
| `import ctypes`, `import ctypes.util` | ✅ (failed with `OSError: dynamic linking not enabled`); `ctypes.pythonapi` is `None`, `find_library("objc")` is `None` |
| Get Add-ons code path (`download_addons`, 18 MB through the relay) | ✅ installed |
| Restart: add-on loads | ✅ (failed in `integrations/mac_titlebar.py` before) |
| Welcome screen, Onigiri main menu (sidebar, Ready to go, decks, stats, activity heatmap), Onigiri menu | ✅ |
| Onigiri › Onigiri Settings | ✅ opens and renders |
| `NotFoundError: insertBefore` from its `web/injector.js:31` at each deck list render | ⚠️ the add-on's own bug, not the port's: `#deck-list-header` and `#deck-list-container` are inside a `<section>`, but it inserts into `.sidebar-expanded-content`; the same on the desktop. Last call of its `init()`, nothing skipped |

### 2026-10-26: Safari and iOS Safari (`tools/test/selftest.py`)

Safari stopped at start with `DataCloneError: The object can not be
cloned` (WebKit lacks COEP `credentialless`; fixes.md). After the fix, the
smoke test's checks plus web view checks (deck list, editor, question and
answer, Stats graphs) in each browser, fresh storage, three page loads:

| Browser | Result |
| --- | --- |
| Safari 27.0.1, macOS (a tab in the user's Safari) | ✅ 32/32, `crossOriginIsolated` true |
| iOS Safari 26.4, iPhone 11 simulator (iOS 26.4) | ✅ 32/32; Kioku lays out at phone width (screenshots) |
| Chrome 155, headless (self-test) | ✅ 32/32 |
| Chrome 155, `smoke.py`, `serve.py` | ✅ 27/27 |
| Chrome 155, `smoke.py`, Worker under `wrangler dev` (headers set by `worker.js`) | ✅ 27/27 |
| iOS Safari, Worker under `wrangler dev` | ✅ starts (language dialog); `require-corp` on every path |
| Card with an image and a script from another origin, with CORS but no CORP (`ONLY=cross`) | ✅ Safari, iOS Safari, Chrome; with sw.js's CORS fetch off, ❌ in Safari (the control) |
| Same, an image with neither CORS nor CORP | Chrome loads it (`credentialless`); Safari, iOS Safari blocked (expected) |

Seen only in WebKit: Anki's editor logs `TypeError: null is not an object
(evaluating 'e.anchor')` when a field gets focus. Its caret save/restore
reads `getSelection()` on the field's shadow root, which WebKit lacks, so
the save is `null` and the restore throws. Typing and saving work (the
note above was typed in Safari); only the caret position isn't restored.
The native iOS app's WKWebView runs the same code. Not fixed.

Safari asks "Do you want to download …?" for exports (iOS); the export
itself is the same blob as in Chrome.

### 2026-10-26 b: a real iPhone (iPhone 15 Pro Max, iOS 27.0.1, Safari 27.0.1)

Served over the LAN with https (`selftest.py iphone`): the page needs a
secure context, so plain `http://<LAN address>` doesn't start
(`crossOriginIsolated` false, no service worker; checked on the phone). A
certificate for the Mac's address (in `build/tls/`, from a local test CA
trusted on the phone for the test, then removed). iOS refused mkcert's
823-day certificate; one valid 180 days worked. Each phase opens in a new
tab and the finished one goes to `about:blank`, as when the app is closed
and opened again (`RELOAD=1`: reload the tab instead). Memory from
Instruments (Activity Monitor template, `xctrace record --device`) and, for
a breakdown, `footprint` of Mac Safari's web process (same WebKit).

The Simulator passed everything (above) but the phone ended the tab
("RangeError: Out of memory" for the user, or a silent reload). Page loads
per phase show the restarts (1 = none):

| Build | Result on the phone |
| --- | --- |
| 32 pool workers, 4 GB wasm memory maximum | killed at start (3 of 5 starts), at import |
| 12 workers, 4 GB | phase 1 passed once, otherwise killed at start, import or restore |
| 12 workers, 1 GB | 35/35; each start with the saved collection killed once (1, 2, 2, 2) |
| + batched storage (`storage.js`) | 35/35; same (1, 2, 2, 2); a start right after an import alone: 1, 1, 1, 1 |
| + rsbridge built for size (now) | **35/35, 1, 1, 1, 1**; reloading the tab (`RELOAD=1`): 35/35, 1, 2, 1, 1 |

| Moment (12 workers, 4 GB, before the fixes) | Footprint |
| --- | --- |
| Loaded, deck list, Add, review | 225–490 MB |
| Import (HSK 1, 25 MB, 311 media files) | spike to 1,891 MB, then ~880 MB |
| Check Database / export | spike to 1,990 MB |
| Reload restoring the saved collection | 1.0–1.4 GB, then ended |

What the memory was (Mac Safari, phone settings): not data (60 MB stored,
318 files) but WebKit's own heap, jumping ~900 MB when Anki's main loop
started and during the import, then settling. Pool workers cost WebKit ~13
MB each (24 vs 12); 2 fewer threads made no difference; one canvas. The
jumps followed the hot code: one 1.4 MB wasm function (rsbridge's whole
dispatch inlined) that Safari's optimizing compiler took hundreds of MB to
compile. Built for size it is 830 KB. In desktop Chrome each pool worker
took ~55–60 MB (`measureUserAgentSpecificMemory`); the app runs 10 threads
at most, so the pool is 12 on phones and 16 elsewhere (`?threads=`); with 4
it deadlocked at start (`ThreadPoolExecutor.submit()`, see
`_start_threads_yielding`). A reload keeps the old page's memory until the
new one runs, so reloading right after heavy use can still be ended once
(Safari then loads the page again by itself). The Simulator's numbers (a 4.5
GB spike while loading) don't match the phone's and aren't used.

#### Performance: web build in Safari vs Kioku's native app, same iPhone

`tools/test/bench_code.py` (Anki 26.09.3 in both; a new collection in a
temporary folder): web `ONLY=bench selftest.py iphone`, native
`ios/tools/devcmd.sh < tools/test/bench_code.py`. Mean of two runs each, ms;
the web build with rsbridge built for size (at opt-level 3 Check Database
took 299 ms, stats 43 ms, export 172 ms).

| Operation | Native | Web | Web is slower |
| --- | ---: | ---: | ---: |
| Python: loop, 3M multiply-adds | 160 | 592 | 3.7× |
| Python: json dumps+loads, 20k records | 23 | 57 | 2.5× |
| Add 1000 notes | 218 | 450 | 2.1× |
| Search all cards ×20 | 23 | 93 | 4.0× |
| Search text ×20 | 11 | 44 | 4.1× |
| Render 300 cards (question+answer) | 49 | 202 | 4.1× |
| Deck tree ×20 | 4 | 26 | 7.1× |
| Answer 200 cards | 90 | 208 | 2.3× |
| Stats graphs ×3 | 3 | 16 | 5.8× |
| Check Database | 28 | 171 | 6.2× |
| Export .apkg (1000 notes) | 29 | 66 | 2.3× |

Start on the phone over the LAN: Python up after 15–27 s, Anki's main loop
after 20–41 s (no HTTP cache: `serve.py` sends `no-store`).

### 2026-11-05: interrupted saves and media sync (issue #10, Chrome, headless)

Local `anki-sync-server`, Anki desktop 25.09.4 (own base folder), Kioku
Android on the emulator, all on one account. Kioku Web was killed with
SIGKILL at chosen IndexedDB transactions (a hook on
`IDBDatabase.prototype.transaction`), then opened again normally so it
synced on its own. Test pictures were uncompressed PNGs (3 MB on disk, small
in a sync zip): the local relay downloads ~1 MB/s, and slower downloads
never put more than 8 MB into one save.

| Test | Result |
| --- | --- |
| Before the fix: killed right after the transaction with `collection.media.db2` and 4 of 14 new pictures | ❌ on the next start Kioku Web's sync sent `removed` for the 7 pictures it listed but had not saved (one an image occlusion picture); Anki desktop moved them to `media.trash`, a fresh Android profile downloaded the notes without them |
| Before the fix: storage quota full during the save (`Storage.overrideQuotaForOrigin`) | ⚠️ "saving files failed" every 10 s only in the console; no loss when the failed save fit in one transaction |
| Recovery: Tools › Check Media › Restore Deleted on Anki desktop, sync, then sync Android | ✅ all 74 pictures back on the server and the phone |
| After the fix: killed right after the first media transaction (media database not saved) | ✅ next start: nothing missing, no `removed` on the server |
| After the fix: killed right after the media database's transaction | ✅ same |
| After the fix: IndexedDB reads fail during loading | ✅ "Kioku couldn't load your saved collection…" note, Anki not started, all 117 saved entries kept; a normal reload starts with everything |
