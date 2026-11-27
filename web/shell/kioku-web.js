// Page side of Kioku's web platform layer (python/kioku_platform): the
// iframes that stand in for Qt WebEngine views, the service worker's request
// relay, the file picker, audio and sockets. Python calls in through window.__kiokuWeb (via
// _kioku_web.run_script); events go back through post(), which reaches
// kioku_platform.web._post() via the wasm export kioku_post.

(function () {
  "use strict";
  const frames = new Map();
  const holders = new Map();
  let parked = null;
  // false while a Qt popup (a menu) is open (WebView.set_touchable)
  let touchable = true;

  function parking() {
    if (!parked) {
      parked = document.createElement("div");
      parked.style.cssText =
        "position: fixed; left: -20000px; top: 0; width: 1000px; height: 800px; visibility: hidden;";
      document.body.appendChild(parked);
    }
    return parked;
  }
  const httpPorts = new Map();
  let nextHttp = 1;
  const queued = [];

  function b64(buffer) {
    const bytes = new Uint8Array(buffer);
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(s);
  }

  // iOS and iPadOS (which reports itself as a Mac with touch)
  function isIOS() {
    return /iPhone|iPad|iPod/.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  // The iOS file picker greys out every file whose extension has no system
  // type when `accept` lists it (.ankiaddon, .apkg, .colpkg: issue #34), so
  // there `accept` is kept only when iOS knows every entry
  const IOS_TYPES = new Set([
    ".txt", ".csv", ".tsv", ".json", ".html", ".htm", ".xml", ".zip", ".pdf",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".svg", ".bmp", ".tif", ".tiff",
    ".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".mp4", ".mov", ".webm",
  ]);
  function iosKnowsAll(accept) {
    return accept.split(",").every((t) => {
      t = t.trim().toLowerCase();
      return !t || t.includes("/") || IOS_TYPES.has(t);
    });
  }

  function href(frame) {
    try {
      return frame.contentWindow.location.href;
    } catch (e) {
      return "";
    }
  }

  const web = (window.__kiokuWeb = {
    // Events for Python. Always from a clean stack: a call into wasm while
    // wasm is running (e.g. page JS run by eval()) would re-enter Python.
    post(event) {
      const text = JSON.stringify(event);
      setTimeout(() => {
        if (window.__kiokuWasmPost) window.__kiokuWasmPost(text);
        else queued.push(text);
      }, 0);
    },

    // Python's entry: evaluate code, return a string ("" on errors)
    safe(code) {
      try {
        const result = (0, eval)(code);
        return result === undefined || result === null ? "" : String(result);
      } catch (e) {
        console.error("kioku:", e);
        return "";
      }
    },

    ready() {
      while (queued.length) window.__kiokuWasmPost(queued.shift());
      return "1";
    },

    // ?safe=1: start without add-ons (kioku/safemode.py)
    safeModeRequested() {
      return new URLSearchParams(location.search).get("safe") === "1" ? "1" : "";
    },

    darkMode() {
      return matchMedia("(prefers-color-scheme: dark)").matches ? "1" : "";
    },

    // Anki's theme, which may differ from the system's: the page around
    // the app and the status bar (theme-color) follow it
    theme(dark) {
      document.documentElement.dataset.theme = dark ? "dark" : "light";
      const color = getComputedStyle(document.documentElement).getPropertyValue("--background").trim();
      for (const meta of document.querySelectorAll('meta[name="theme-color"]')) {
        meta.removeAttribute("media");
        meta.content = color;
      }
      return "1";
    },

    origin() {
      return location.origin;
    },

    timeZone() {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    },

    // Web views -----------------------------------------------------------

    // Set up a page in one of the iframes (WebView.BRIDGE runs this first):
    // window.__kiokuNative for kioku.webscripts.PRELUDE, with channel calls
    // answered through window.__kiokuResolve(); links to other sites go to
    // Python (acceptNavigationRequest); keys the page leaves alone go to Qt,
    // like QtWebEngine passes them on, so Anki's shortcuts work
    bridge(win) {
      const frame = win.frameElement;
      const id = Number(frame.dataset.kioku);
      const gen = Number(frame.dataset.gen);
      const pending = {};
      let next = 1;
      win.__kiokuNative = {
        send(name, text) {
          web.post({ type: "message", view: id, name, text });
        },
        call(text) {
          return new win.Promise((resolve, reject) => {
            const call = next++;
            pending[call] = [resolve, reject];
            web.post({ type: "channel", view: id, gen, call, text });
          });
        },
      };
      win.__kiokuResolve = (call, ok, value) => {
        const p = pending[call];
        delete pending[call];
        if (p) (ok ? p[0] : p[1])(value);
      };
      win.document.addEventListener("click", (e) => {
        const a = e.target && e.target.closest && e.target.closest("a[href]");
        if (!a || e.defaultPrevented) return;
        let url;
        try {
          url = new URL(a.getAttribute("href"), win.location.href);
        } catch (x) {
          return;
        }
        if (url.origin === location.origin || url.protocol === "javascript:") return;
        e.preventDefault();
        web.post({ type: "navigate", view: id, url: url.href });
      });
      const editable = (t) =>
        t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ""));
      for (const type of ["keydown", "keyup"]) {
        win.addEventListener(type, (e) => {
          if (e.defaultPrevented || e.isComposing) return;
          const target = e.composedPath ? e.composedPath()[0] : e.target;
          const modified = e.ctrlKey || e.metaKey || e.altKey;
          if (editable(target) && !modified && !/^(Escape|F\d+)$/.test(e.key)) return;
          const host = frame.parentElement && frame.parentElement.closest(".qt-window");
          if (!host) return;
          host.dispatchEvent(
            new KeyboardEvent(type, {
              key: e.key, code: e.code, keyCode: e.keyCode, which: e.which,
              ctrlKey: e.ctrlKey, shiftKey: e.shiftKey, altKey: e.altKey, metaKey: e.metaKey,
              repeat: e.repeat, bubbles: true, cancelable: true,
            }),
          );
        });
      }
    },

    // An iframe loads only while it is in the document, but Anki keeps
    // some views hidden until their page has loaded (pycmd("domDone")).
    // So pages load in an off-screen parking spot; Qt embeds a placeholder
    // (the foreign window), and adopt() moves the iframe into it with
    // moveBefore(), which keeps the page (appendChild would reload it).
    create(id) {
      const frame = document.createElement("iframe");
      frame.dataset.kioku = String(id);
      frame.dataset.gen = "0";
      frame.setAttribute("allow", "autoplay; clipboard-read; clipboard-write; fullscreen");
      frame.style.cssText = "border: 0; display: block; width: 100%; height: 100%; background: white;";
      if (!touchable) frame.style.pointerEvents = "none";
      frame.addEventListener("load", () => {
        web.post({ type: "load", view: id, gen: Number(frame.dataset.gen), url: href(frame) });
      });
      const holder = document.createElement("div");
      holder.style.cssText = "display: block; overflow: hidden;";
      // Qt 6.11's ~QWasmWindow removes its canvas and accessibility
      // container from the window element, which a foreign window never
      // got; the NotFoundError would end Qt's event loop
      holder.removeChild = function (child) {
        return child.parentNode === this ? Node.prototype.removeChild.call(this, child) : child;
      };
      // while a Qt popup is open the iframe takes no taps and the holder
      // gets them; Qt hands a tap on a foreign window to that window only,
      // so the popup wouldn't close: Python closes it (popupTap)
      holder.addEventListener("pointerdown", () => {
        if (!touchable) web.post({ type: "popupTap" });
      });
      parking().appendChild(frame);
      frames.set(id, frame);
      holders.set(id, holder);
    },

    adopt(id, tries) {
      const frame = frames.get(id);
      const holder = holders.get(id);
      if (!frame || !holder || frame.parentNode === holder) return;
      if (!holder.isConnected) {
        if ((tries || 0) < 120) requestAnimationFrame(() => web.adopt(id, (tries || 0) + 1));
        return;
      }
      if (holder.moveBefore && frame.isConnected) holder.moveBefore(frame, null);
      else holder.appendChild(frame);
    },

    // the element Qt embeds as a foreign window (_kioku_web.element_handle)
    frame(id) {
      return holders.get(id);
    },

    load(id, url, gen) {
      const frame = frames.get(id);
      if (!frame) return;
      frame.dataset.gen = String(gen);
      frame.src = url;
    },

    // the frame takes the keyboard focus (QWebEngineView.setFocus)
    focus(id) {
      const frame = frames.get(id);
      if (frame && frame.contentWindow) frame.contentWindow.focus();
    },

    reload(id) {
      const frame = frames.get(id);
      if (frame) frame.contentWindow.location.reload();
    },

    go(id, delta) {
      const frame = frames.get(id);
      if (frame) frame.contentWindow.history.go(delta);
    },

    title(id) {
      const frame = frames.get(id);
      try {
        return frame.contentDocument.title;
      } catch (e) {
        return "";
      }
    },

    // QWebEnginePage.runJavaScript: the value of the last expression, as
    // JSON in an "eval" event (queued after what the script posted)
    eval(id, js, cb) {
      const frame = frames.get(id);
      let value = "null";
      if (frame && frame.contentWindow) {
        try {
          const result = frame.contentWindow.eval(js);
          value = JSON.stringify(result === undefined ? null : result) ?? "null";
        } catch (e) {
          console.error("kioku: eval in view " + id + ":", e);
        }
      }
      if (cb) web.post({ type: "eval", view: id, cb, value });
      return "";
    },

    resolve(id, call, ok, value) {
      const frame = frames.get(id);
      try {
        frame.contentWindow.__kiokuResolve(call, ok, value);
      } catch (e) {}
    },

    // Off while a Qt popup (a menu) is open: a tap on a page then goes to
    // the holder, which reports it (popupTap) and Python closes the popup
    touchable(on) {
      touchable = on;
      for (const frame of frames.values()) frame.style.pointerEvents = on ? "" : "none";
    },

    // Qt sizes a foreign window's element in width only
    size(id, height) {
      const holder = holders.get(id);
      if (holder) holder.style.height = height + "px";
    },

    background(id, color) {
      const frame = frames.get(id);
      if (frame) frame.style.background = color;
    },

    // Like QtWebEngine's zoom factor: the page lays out in a viewport
    // 1/factor the size and is scaled up to fill the view. CSS zoom on the
    // page's <html> left Safari's viewport at full size, so a zoomed-in
    // page filled only 1/factor of the view (blank below the reviewer's
    // card), and a page load dropped it
    zoom(id, factor) {
      const frame = frames.get(id);
      if (!frame) return;
      const size = factor === 1 ? "100%" : `${100 / factor}%`;
      frame.style.width = size;
      frame.style.height = size;
      frame.style.transformOrigin = "0 0";
      frame.style.transform = factor === 1 ? "" : `scale(${factor})`;
    },

    // Only stop the page: once embedded, the element belongs to Qt, which
    // removes it with the foreign window (an exception thrown there, e.g.
    // for an element already gone, would end Qt's event loop)
    destroy(id) {
      const frame = frames.get(id);
      frames.delete(id);
      holders.delete(id);
      if (frame) {
        frame.src = "about:blank";
        if (frame.parentNode === parked) frame.remove();
      }
    },

    // Service worker relay ---------------------------------------------------

    respond(id, status, headers, body) {
      const port = httpPorts.get(id);
      httpPorts.delete(id);
      if (port) port.postMessage({ status, headers: JSON.parse(headers), body }, [body.buffer]);
    },

    // Files ---------------------------------------------------------------

    // Choose files and copy them into the wasm file system; posts "picked"
    pick(multi, accept) {
      const input = document.createElement("input");
      input.type = "file";
      input.multiple = !!multi;
      if (accept && !(isIOS() && !iosKnowsAll(accept))) input.accept = accept;
      input.style.display = "none";
      document.body.appendChild(input);
      let done = false;
      const finish = (paths) => {
        if (done) return;
        done = true;
        input.remove();
        web.post({ type: "picked", paths });
      };
      input.addEventListener("cancel", () => finish([]));
      input.addEventListener("change", async () => {
        const FS = window.__kiokuFS;
        const dir = "/tmp/picked/" + Date.now();
        FS.mkdirTree(dir);
        const paths = [];
        for (const file of input.files) {
          const path = dir + "/" + file.name.replace(/\//g, "_");
          FS.writeFile(path, new Uint8Array(await file.arrayBuffer()));
          paths.push(path);
        }
        finish(paths);
      });
      input.click();
      return "1";
    },

    // Hand a file from the wasm file system to the browser as a download
    download(path, name) {
      const data = window.__kiokuFS.readFile(path);
      const url = URL.createObjectURL(new Blob([data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      return "1";
    },

    // Save changed files to IndexedDB (main.cpp kioku_load_storage)
    persist() {
      if (window.__kiokuPersist) window.__kiokuPersist();
      return "1";
    },

    // Audio and TTS (kioku_platform.audio) ---------------------------------

    // Play a file from the wasm file system; posts "audio_done" with the
    // token once it has ended, failed or been stopped
    play(path, token) {
      web.stopAudio();
      let data;
      try {
        data = window.__kiokuFS.readFile(path);
      } catch (e) {
        web.post({ type: "audio_done", token });
        return "";
      }
      const url = URL.createObjectURL(new Blob([data]));
      const a = (audio = new Audio(url));
      const done = () => {
        if (a.done) return;
        a.done = true;
        URL.revokeObjectURL(url);
        if (audio === a) audio = null;
        web.post({ type: "audio_done", token });
      };
      a.stopped = done;
      a.onended = done;
      a.onerror = done;
      a.play().catch((e) => {
        console.warn("kioku: audio", e.message);
        done();
      });
      return "1";
    },

    stopAudio() {
      if (audio) {
        audio.pause();
        audio.stopped();
      }
      return "1";
    },

    pauseAudio() {
      if (audio) audio.paused ? audio.play() : audio.pause();
      return "1";
    },

    seekAudio(secs) {
      if (audio) audio.currentTime = Math.max(0, audio.currentTime + secs);
      return "1";
    },

    voices() {
      return JSON.stringify(
        speechSynthesis.getVoices().map((v) => ({ name: v.name, lang: v.lang, uri: v.voiceURI })),
      );
    },

    // Speak with the Web Speech API; posts "tts_done" with the token
    speak(text, uri, lang, rate, token) {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.voice = speechSynthesis.getVoices().find((v) => v.voiceURI === uri) || null;
      u.lang = lang;
      u.rate = rate;
      let finished = false;
      u.onend = u.onerror = () => {
        if (finished) return;
        finished = true;
        web.post({ type: "tts_done", token });
      };
      speechSynthesis.speak(u);
      return "1";
    },

    stopSpeaking() {
      speechSynthesis.cancel();
      return "1";
    },

    pauseSpeaking() {
      speechSynthesis.paused ? speechSynthesis.resume() : speechSynthesis.pause();
      return "1";
    },
  });

  let audio = null;

  // Emscripten's sockets connect as WebSockets to ws://<host>:<port>/;
  // send them to the relay next to the page (tools/serve.py), which
  // passes them on over TCP
  const NativeWebSocket = window.WebSocket;
  window.WebSocket = class extends NativeWebSocket {
    constructor(url, protocols) {
      const u = new URL(url);
      if (u.host !== location.host) {
        const scheme = location.protocol === "https:" ? "wss:" : "ws:";
        url = `${scheme}//${location.host}/__relay/${u.hostname}:${u.port || 80}`;
      }
      super(url, protocols);
    }
  };
  // the voice list fills in asynchronously
  if (window.speechSynthesis) speechSynthesis.getVoices();
  // save /home/web_user (storage.js) on a timer and when the page goes
  // away; Python also asks after collection operations
  setInterval(() => web.persist(), 10000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") web.persist();
  });
  window.addEventListener("pagehide", () => web.persist());

  navigator.serviceWorker.addEventListener("message", (event) => {
    const msg = event.data;
    if (!msg || msg.type !== "http") return;
    const id = nextHttp++;
    httpPorts.set(id, event.ports[0]);
    web.post({
      type: "http",
      id,
      method: msg.method,
      url: msg.url,
      headers: msg.headers,
      body: msg.body ? b64(msg.body) : "",
    });
  });
})();
