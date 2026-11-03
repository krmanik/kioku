# Fixes log: Kioku (unmodified Anki desktop) in a browser tab

Every problem found while bringing Kioku's iOS/Android design to
WebAssembly, what caused it, and where the fix lives. Newest at the bottom
of each section. Add to this file whenever something new is fixed.

Background: `sys.platform` is `"emscripten"`, so Anki takes its Linux code
paths, as on the phones. Everything is built with Emscripten 4.0.7, the
version Qt 6.11's prebuilt WebAssembly libraries use (see
[architecture.md](architecture.md)).

## Building: Anki's Rust core

All crates are patched from copies in `deps/patched/` that cargo picks up
with `--config patch.crates-io…` (`tools/build_rust.sh`); Anki's own source
is unchanged.

| Problem | Cause | Fix |
| --- | --- | --- |
| tokio: `Only features sync,macros,io-util,rt,time are supported on wasm` | emscripten counts as `target_family = "wasm"`; Anki enables `fs`, `rt-multi-thread`, `signal` | `--cfg tokio_unstable`, which lifts the check |
| mio: `file not found for module selector` / `waker`, `This wasm target is unsupported by mio` | mio has no emscripten backend | `patches/mio-1.0.4.patch` (emscripten treated like hermit/nto: poll selector, plain `accept`) plus `--cfg mio_unsupported_force_poll_poll --cfg mio_unsupported_force_waker_pipe` |
| mio: `sockaddr_in has no field sin_len`, `cannot find eventfd` | the hermit lists also carry BSD/eventfd specifics | those spots left out of the patch; pipe waker forced by the cfg |
| tokio: `cannot find crate socket2` | tokio leaves out socket2 on every wasm target | `patches/tokio-1.47.1.patch` (only on non-emscripten wasm); `get_peer_cred` via `impl_noproc` |
| socket2: `cannot find type IovLen` | emscripten's `msghdr.msg_iovlen` (musl) missing from the list | `patches/socket2-0.6.0.patch` (`c_int`) |
| rslib: `no method timeout/use_rustls_tls/http1_only`, `wrap_stream`, `Certificate`, Send errors | reqwest switches to its browser-fetch client on `target_arch = "wasm32"`, which lacks that API (and needs wasm-bindgen) | `patches/reqwest-0.12.23.patch`: the native hyper client on emscripten (sockets are emulated by Emscripten) |
| rslib: `unresolved import tokio::io::AsyncReadExt` | `io-util` came only through reqwest's native backend | `io-util` in tokio's defaults (tokio patch) |
| rustls: `SystemRandom: SecureRandom is not satisfied` | ring enables its RNG only for listed targets | `patches/ring-0.17.14.patch` (emscripten → getrandom/getentropy) |
| link: `--shared-memory is disallowed … not compiled with atomics` | Rust's prebuilt std for emscripten has no atomics | nightly `-Zbuild-std` with `-C target-feature=+atomics,+bulk-memory,+mutable-globals` |
| link: same error for `sqlite3.o` | cc builds Rust's bundled C without `-pthread` | `CFLAGS_wasm32_unknown_emscripten=-pthread` (and CXXFLAGS) |
| link: `undefined symbol __cpp_exception` | Rust on emscripten unwinds with wasm exception handling | first `-fwasm-exceptions`, then see the Qt row below |
| link: `SUPPORT_LONGJMP=emscripten is not compatible with -fwasm-exceptions` / `undefined emscripten_longjmp` | prebuilt Qt uses Emscripten's JS setjmp/longjmp, which can't be mixed with wasm EH | Rust built with `panic=abort` (`-Zbuild-std=std,panic_abort`), nothing uses `-fwasm-exceptions` |
| Anki's `ios/deps/anki/Cargo.lock` rewritten (patch entries, tokio 1.50, mio 1.1) | cargo updates the lock file of the workspace it builds | restored with `git checkout`; `build_rust.sh` swaps in its own copy (`build/anki-Cargo.lock`) and restores Anki's on exit |
| Panic `fd != -1` (std `from_raw_fd`) as soon as Anki checks for updates | mio's `pipe::new_raw` creates no pipe on unlisted targets and returns `[-1, -1]` | emscripten added to mio's `pipe()` + `fcntl` list (mio patch) |
| tokio's signal driver wraps a socketpair fd | emscripten has no working `socketpair()`; a tab gets no signals | on emscripten the signal driver polls the read end of an unused pipe (tokio patch) |

## Building: CPython

| Problem | Cause | Fix |
| --- | --- | --- |
| `configure: --enable-wasm-dynamic-linking only applies to Emscripten` | `Tools/wasm/emscripten build -- args` also passes the args to the native build Python | steps run one by one (`tools/build_python.sh`) |
| `clang: unknown argument -mgc` | 3.14's wasm-gc call trampoline needs a newer LLVM than Emscripten 4.0.7's | the trampoline module is left empty (`patches/cpython-3.14.0-emsdk-4.0.7.patch`); CPython falls back to the JS trampoline… |
| …later: Asyncify crash (`unreachable` under `_PyEM_TrampolineCall_inner`) | Asyncify can't unwind through the JS trampoline's frame | CPython built without `PY_CALL_TRAMPOLINE` (plain indirect calls) |
| `use of unknown builtin __builtin_wasm_ref_is_null_extern` | same LLVM gap, in the JSPI async-stdin hooks | hooks route straight to the original syscalls |
| `ReferenceError: resolveGlobalSymbol is not defined` at start | a constructor installs JS written for Emscripten ≥ 4.0.11 | no longer a constructor |
| `undefined symbol _Py_LibHacl_Hacl_Hash_MD5_*` | the HACL hash objects aren't in `libpython3.14.a` | link `Modules/_hacl/*.o` |
| ctypes: `Unable to grow wasm table` | CPython's own link sets it, ours didn't | `-sALLOW_TABLE_GROWTH` |
| Stale objects kept the trampoline after reconfiguring | CFLAGS changes don't trigger rebuilds | `make clean` before `make-host` |
| Onigiri add-on: `import ctypes` failed (`OSError: dynamic linking not enabled`), also `import ctypes.util` | CPython is linked statically: no `dlopen()`, but `ctypes` opens the main program (`PyDLL(None)`) when imported and `ctypes.util` does too (`CDLL(None)`, for `dl_iterate_phdr`) | `Lib/ctypes` in `patches/cpython-3.14.0-emsdk-4.0.7.patch`: `pythonapi` is `None` on emscripten if that fails; `ctypes.util` skips the library listing on emscripten. Loading a library still raises `OSError`, which add-ons expect off their platform. The stdlib is packed at link time and isn't a link dependency: `rm build/cmake/kioku.js` before `tools/build.sh` |

## Building: PyQt6 and the app

| Problem | Cause | Fix |
| --- | --- | --- |
| sip-build: `qmake -query failed returning 127` | aqt's wasm qmake wrapper calls host qmake relative to the current directory | `tools/fetch_deps.sh` links host Qt from the Kioku repo and fixes the wrapper |
| `no member named NameType in QTimeZone`, `no QSystemSemaphore`, `QSharedMemory::lock`, `QDateTime::timeZone` | Qt for WebAssembly leaves out `timezone` and `systemsemaphore`; PyQt has no feature flags for them | new sip features `PyQt_TimeZone`, `PyQt_SystemSemaphore` (`patches/pyqt6-wasm.patch`, `tools/gate_timezone.py`), disabled in `tools/gen_pyqt.sh` |
| QtNetwork: missing `qsslcertificate.h`, `QNetworkInterface`, multicast | no OpenSSL and no `networkinterface` in Qt for WebAssembly | `--disabled-feature PyQt_SSL`, new `PyQt_NetworkInterface` |
| Regenerating PyQt rebuilt all 900 sources | sip-build rewrites every file | `gen_pyqt.sh` generates into a new folder and copies only changed files (`rsync -c`) |
| `No module named PyQt6` | the package needs an `__init__.py` | Kioku's `shared/python/PyQt6` overlay is packed as `/app/PyQt6` (also provides the QtWebEngine stand-ins) |
| `No module named js` (urllib3) | urllib3 takes `sys.platform == "emscripten"` for Pyodide | `tools/prepare_site.sh` makes that import optional |
| Asyncify link: 94 MB wasm, 5 min | Asyncify instruments everything | accepted for now (`KIOKU_ASYNCIFY`); JSPI needs Qt from source |

## Runtime

| Problem | Cause | Fix |
| --- | --- | --- |
| Startup hangs after the first-run dialogs | Anki's GUI waits (`MediaServer.getPort()`) for its server thread to listen, which a tab can't | `http.setup()` replaces `run`/`getPort`; requests come through the service worker |
| Anki took `--kioku` for a file to import | the launch flag reached `sys.argv` | `main.cpp` doesn't pass it on |
| Main thread hangs as soon as pages load (stack: `kioku_post` → `lock.acquire`) | `ThreadPoolExecutor.submit` starts a thread from the main thread; `Thread.start()` waits for it, and a new Web Worker can only start once the main thread yields | `QT_WASM_PTHREAD_POOL_SIZE` 32 (Qt sets 4; a later `-sPTHREAD_POOL_SIZE` is overridden); HTTP requests are handed to the pool by a dispatcher thread, so the main thread never starts threads for them |
| Pages: "127.0.0.1 refused to connect" | the app page is cross-origin isolated, so iframes need COEP | `sw.js` adds COEP/CORP to every response |
| Anki forbids framing its pages | `frame-ancestors 'none'` | rewritten to `'self'` (`http.py`) |
| A picture whose file name has `#` or `%xx` in it didn't show (e.g. an image occlusion card's picture: header and Toggle Masks only; GitHub issue #10); on the desktop it does | the editor writes `src="fig%20%232.png"`; `http.py` decoded the path, then werkzeug's test client decoded it again and cut it at the `#` | the path goes to werkzeug still percent-encoded, which decodes it once, as waitress does on the desktop |
| Web views 150 px tall | Qt sets only the width of a foreign window's element | height from the container's resize events (`webview._Resizes`) |
| `pycmd is not defined` in every page | document-ready scripts were wrapped in a DOMContentLoaded function, so Anki's `var pycmd` became local | each script is a separate file; document-ready ones are added as `<script>` elements at DOMContentLoaded |
| Inline scripts would be blocked in the editor (`script-src http://127.0.0.1:port/_anki/`) and SvelteKit pages | strict CSPs | Kioku's scripts come from `/_anki/__kioku/…` URLs |
| `runJavaScript` blocked in the editor | eval from the parent counts against the page's CSP | `'unsafe-eval'` added where `script-src` is restricted (header and SvelteKit meta) |
| Closing Add killed Qt's event loop (`NotFoundError: removeChild`) | Qt 6.11's `~QWasmWindow` removes its canvas from the window element, which a foreign window never had | the placeholder's `removeChild` ignores children it doesn't have; `destroy()` only blanks the iframe (Qt removes the element) |
| Add saved the last field empty | `saveNow()`'s callback ran before the field-save message the script had just sent | eval results come back as events through the same ordered queue |
| Space, 1–4 and other shortcuts did nothing | keys went to the iframe's document; Qt never saw them | keys the page leaves alone are re-dispatched on Qt's window element (`bridge()` in kioku-web.js) |
| Import page blank | Anki keeps it hidden until `domDone`, but an iframe outside the document never loads | pages load in an off-screen parking spot; Qt embeds a placeholder, and the iframe moves in with `moveBefore()` |
| Bottom bar off the page | the main window kept its desktop size (823–857 px on a 700 px page); `WindowMaximized` didn't fit it, and Anki restores geometry when the profile opens | `_fill_screen()` keeps the main window at the screen's available geometry (Show/Resize, profile open, screen changes) |
| App trapped (`unreachable` in `emscripten_futex_wait`, Backend mutex) as soon as the profile opened | `/home/web_user` mounted as IDBFS, even without `autoPersist` and loading (a MEMFS mount works; cause not found) | `shell/storage.js` mounts MEMFS and syncs it with `IDBFS.syncfs()`/`queuePersist()` |
| Loading saved files from `main()` (`EM_ASYNC_JS`) broke Qt's event loop | Asyncify suspended `main()` before `app.exec()` | load in `preRun` with a run dependency (`--pre-js shell/storage.js`) |
| WebSockets to `ws://ankiweb.net:443/` went nowhere | Emscripten's sockets are WebSockets; nothing spoke TCP | `WebSocket` wrapped on the app page → `/__relay/host:port`; `tools/serve.py` relays to TCP (allowlisted hosts) |
| TLS would fail with no roots | rustls with native roots finds no system store in the wasm file system | `SSL_CERT_FILE` = `/site/certifi/cacert.pem` before Anki starts |
| `col.sync_login()` from the main thread never returned | the main thread blocked in Rust; WebSocket events need it back in the browser's event loop | network calls on background threads (as Anki's sync UI does) |
| A Python-only change took a 5-minute relink | the app's Python was `--preload-file`d at link time | `tools/pack_app.sh` packs it into `app.data` (loader `app-data.js` linked once with `--pre-js`, file list in `app-data.js.metadata`) on every build |
| Installing an add-on failed (`No module named 'rpds'`) | jsonschema (manifest check) → referencing → rpds-py, a Rust extension | `tools/build_rpds.sh` builds it for wasm, registered as built-in `rpds` |
| `rpds.HashTrieMap({...})` crashed (memory access out of bounds) | built with Kioku's abi3 (3.9) pyo3 config | built against the real interpreter: `tools/pyo3/cp314-wasm32.cfg` (3.14, 32-bit) |
| HyperTTS: `No module named '_ssl'`; Get Add-ons impossible | CPython built without OpenSSL; libffi's `.pc` still pointed at the repo's old folder, so that rebuild failed too | `tools/build_openssl.sh` (OpenSSL 3.5.4, `-pthread`), CPython `--with-openssl`, `libssl.a`/`libcrypto.a` linked; `.pc` prefixes fixed |
| requests: `[Errno 50] Protocol not available` | Emscripten's sockets reject `setsockopt(TCP_NODELAY)` and `getsockopt(SO_TYPE)` (ssl) | `kioku_platform._ignore_socket_options()` |
| requests: read timeout at once | Emscripten's `poll()` ignores its timeout | `-Wl,--wrap=poll`: worker threads re-poll every 2 ms until the timeout (`src/main.cpp`) |
| AMBOSS: login dialog showed a broken page | it loads `http://localhost:<port>/_addons/…`, another origin than the page's `127.0.0.1`, so the service worker never saw it (404 from serve.py) | `WebView.load_url` rewrites `localhost:<port>` to `127.0.0.1:<port>` |
| AMBOSS: `ambossAddon is not defined`, its CDN script blocked | COEP `require-corp` blocks cross-origin scripts without CORP headers | COEP `credentialless` (serve.py, sw.js): still cross-origin isolated in Chrome/Firefox; Safari: see below |
| AMBOSS/HyperTTS hosts refused by the relay (403) | allowlist had only AnkiWeb | relay checks `Origin` (only the app page may use it) and allows any host on 443 |
| AMBOSS login would hang | it logs in from a pycmd handler on the GUI thread; the relay's data arrives as WebSocket events, which only run once the main thread yields | the `poll()` wrapper yields on the main thread with `emscripten_sleep()` (Asyncify) |
| File › Import had no file picker | `pick_files` was a stub | `<input type=file>` opened from the triggering click, files copied into the wasm file system |
| The app worked only from `http://127.0.0.1:<port>` (a `localhost` or real domain URL: blank pages) | Anki's URLs (`mw.serverURL()`, `webBundlePath`, CSPs) and Kioku's auth script name `127.0.0.1`, which is only the page's origin there | `http.setup()` gets `location.origin` and points them at it (`http.local_url`, `_local_text`); the auth script's host check is rewritten in `WebView.set_user_scripts()` |
| Cloudflare: `kioku.wasm` (100 MB) and `kioku.data` (34 MB) not accepted | 25 MiB per file | `tools/dist.sh` stores them brotli-compressed; `cloudflare/worker.js` serves them with `Content-Encoding: br` |
| Cloudflare relay: connection opened, then nothing (read timeouts) | Workers' WebSockets give binary messages as Blobs (the standard default with current compatibility dates); `new Uint8Array(blob)` is empty | `server.binaryType = "arraybuffer"` |
| Chinese, Japanese, Korean, Thai and Oriya showed as boxes in Qt's widgets (language list, Browse); web pages were fine | Qt for WebAssembly brings only DejaVu fonts and can't use the system's | Noto fonts (`tools/fetch_deps.sh`, pinned, checksummed) packed into kioku.data at `/fonts`; `_add_fonts()` adds them once `AnkiApp` exists and makes them the fallback for their scripts (`addApplicationFallbackFontFamily`) |
| Browse's Created column (and every date from Anki's core) in UTC, the scheduler's day cutoff at 4 am UTC | chrono (Rust) reads the zone from `/etc/localtime`, which the wasm file system lacked; Python's dates were right (Emscripten asks JavaScript) | `_set_timezone()` copies the browser's zone (`Intl` name) from tzdata (`tools/fetch_deps.sh`, packed as `/site/tzdata`) to `/etc/localtime` before the backend starts |
| Safari and every iOS browser: `Unhandled Promise Rejection: DataCloneError: The object can not be cloned`, the app never started | WebKit has no COEP `credentialless`, so the page wasn't cross-origin isolated and Emscripten couldn't hand the shared wasm memory to its threads | WebKit-only browsers (`AppleWebKit` without `Chrome/` in the user agent) get `require-corp`: `embedder_policy()` in `tools/serve.py`, `embedderPolicy()` in `cloudflare/worker.js`, `EMBEDDER_POLICY` in `shell/sw.js` (Anki's pages) |
| Safari with `require-corp`: cards' remote images and add-ons' CDN scripts blocked (they load in Chrome/Firefox with `credentialless`) | `require-corp` wants a `Cross-Origin-Resource-Policy` header on every cross-origin resource | WebKit only: `shell/sw.js` fetches cross-origin `no-cors` GETs with CORS and adds the header; hosts without CORS stay blocked |
| Cloudflare: the embedder policy can't depend on the browser | `_headers` is static | the Worker runs first for every request (`run_worker_first: true`) and sets COOP/COEP itself; `_headers` removed |
| `orjson is missing; DB operations will be slower` at every start | orjson (Rust) wasn't built for wasm; Anki fell back to `json` | `tools/build_orjson.sh` builds it like rpds-py (from a copy of the sdist without its `.cargo/config.toml`, whose vendored-crates source `-Zbuild-std` can't use), registered as built-in `orjson.orjson`; its Python half is in site-packages again. markupsafe's `_speedups.c` is compiled in too (`markupsafe._speedups`) |
| Every window had a desktop frame (title, maximize, close) above Kioku's own title bar with Back | Qt for WebAssembly draws a frame for each top-level window | `_frameless_windows()`: `FramelessWindowHint` set on each window's `QWindow` when it shows (`QWidget.setWindowFlag()` would hide the window and end a dialog's `exec()`) |
| iPhone: "RangeError: Out of memory", or Safari reloading the tab | the pool's 32 Web Workers (~55 MB each) and a 4 GB shared wasm memory reservation | the page picks the pool (`kiokuThreads`: 12 on phones, 16 elsewhere; `PTHREAD_POOL_SIZE=Module.kiokuThreads`) and the memory (`wasmMemory`: 1 GB on phones, else the largest of 4/2/1 GB that can be reserved); Python's `Thread.start()` yields while it waits on the main thread, a fallback for threads beyond the pool |
| iPhone: the tab ended right after start with a saved collection, and while importing | Emscripten's IDBFS sync handles every changed file at once (all structured-cloned into one transaction, each with its spare capacity; all read back together on start), and MEMFS grows files over 1 MB by 1.125x, so a 30 MB media file was copied ~30 times while written | `shell/storage.js` syncs with its own loop on IDBFS's helpers: changed files only, ≤ 8 MB per transaction when saving (exact-size copies, which also trims the files kept in memory), 8 files per transaction when loading, each transaction finished before the next; MEMFS grows files 2x |
| iPhone: the tab still ended once at most starts after real use (right after "Starting main loop"), and the Simulator and Mac Safari showed WebKit's heap jumping ~900 MB there and during imports, then settling | rslib's whole backend dispatch was inlined into one 1.4 MB wasm function (pyo3's trampoline for `Backend.command`); once hot, JavaScriptCore's optimizing tier compiled it, transiently taking hundreds of MB | `tools/build_rust.sh` builds rsbridge with `opt-level = "s"`: that function is 830 KB, the wasm 97 MB (was 100), and every start on the iPhone opened the first time. rsbridge, rpds and orjson each bundle Rust's std: linked with `--allow-multiple-definition` (`rust_eh_personality` clashed) |
| iPhone home screen app (iOS 27): a blur over the top of the screen | iOS 27 draws it over a home screen app's top edge, whatever `apple-mobile-web-app-status-bar-style` says | `shell/app.html`: a fixed 11 px strip at the top in `display-mode: standalone`, painted invisibly (background clipped to its text, which it has none of); iOS takes the status bar's color from it |
| Status bar white in the dark theme; the page around the app followed the system's theme, not Anki's (Preferences › Theme) | the strip was always light, and the page only knew `prefers-color-scheme` | `_follow_theme()` tells the page Anki's theme (`main_window_did_init`, `theme_did_change`); `theme()` in `shell/kioku-web.js` sets `data-theme`, and the page background, the strip and `theme-color` follow it |
| View › Zoom In: at 110% the reviewer's card ended a tenth short of its view, blank below; a page load dropped the zoom | the zoom factor was CSS `zoom` on the page's `<html>`, which in Safari keeps the viewport at full size | `zoom()` in `shell/kioku-web.js` lays the iframe out 1/factor the size and scales it up (`transform`), like QtWebEngine's page zoom; it's on the iframe, so it stays across loads |
