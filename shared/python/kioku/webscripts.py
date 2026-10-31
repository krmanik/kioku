"""JavaScript injected into every page by the web view backends.

The backends differ only in how a page talks to Python; each one installs a
small BRIDGE script first that defines window.__kiokuNative:

    __kiokuNative.send(name, text)   fire-and-forget message ("console",
                                     "selection", "tap")
    __kiokuNative.call(text)         a web channel call; returns a Promise of
                                     the JSON-encoded result
"""

import json
import re

# Event names used with __kiokuNative.send()
CONSOLE = "console"
SELECTION = "selection"
TAP = "tap"

# Stand-in for qwebchannel.js: calls on channel.objects.<name>.<method>(...)
# go to Python. Also console capture, selection and tap tracking.
PRELUDE = r"""
(function () {
    if (window.__kioku) return;
    window.__kioku = true;
    var native = window.__kiokuNative;
    function post(level, args) {
        try {
            var parts = Array.prototype.map.call(args, function (a) {
                if (typeof a === "string") return a;
                try { return JSON.stringify(a); } catch (e) { return String(a); }
            });
            native.send("console", JSON.stringify({
                level: level, msg: parts.join(" "), src: String(location.href)
            }));
        } catch (e) {}
    }
    ["log", "info", "warn", "error", "debug"].forEach(function (name) {
        var orig = console[name];
        console[name] = function () {
            post(name, arguments);
            if (orig) orig.apply(console, arguments);
        };
    });
    window.addEventListener("error", function (e) {
        post("error", [e.message + " (" + e.filename + ":" + e.lineno + ")"]);
    });
    window.addEventListener("unhandledrejection", function (e) {
        var r = e.reason;
        post("error", ["Unhandled promise rejection: " + (r && (r.stack || r))]);
    });
    document.addEventListener("selectionchange", function () {
        try { native.send("selection", String(window.getSelection())); }
        catch (e) {}
    });
    // Qt doesn't see taps on a page, so QCursor.pos() stayed where Qt last
    // saw one: menus a page opens there (the review screen's More) showed
    // at the top left. Where in the view, as fractions of its size.
    window.addEventListener("pointerdown", function (e) {
        try {
            var v = window.visualViewport;
            var x = v ? e.clientX - v.offsetLeft : e.clientX;
            var y = v ? e.clientY - v.offsetTop : e.clientY;
            var w = v ? v.width : window.innerWidth;
            var h = v ? v.height : window.innerHeight;
            if (w > 0 && h > 0) {
                native.send("tap", JSON.stringify({x: x / w, y: y / h}));
            }
        } catch (e) {}
    }, true);

    window.qt = window.qt || {};
    window.qt.webChannelTransport = window.qt.webChannelTransport || {};
    function makeObject(objName) {
        return new Proxy({}, {
            get: function (target, method) {
                if (typeof method !== "string" || method === "then") return undefined;
                return function () {
                    var args = Array.prototype.slice.call(arguments);
                    var cb = null;
                    if (args.length && typeof args[args.length - 1] === "function") {
                        cb = args.pop();
                    }
                    native.call(JSON.stringify({
                        obj: objName, method: method, args: args
                    })).then(function (reply) {
                        if (cb) cb(JSON.parse(reply));
                    }, function (err) {
                        console.error("channel call " + objName + "." + method + " failed: " + err);
                    });
                };
            }
        });
    }
    window.QWebChannel = function (transport, initCallback) {
        var cache = {};
        this.objects = new Proxy(cache, {
            get: function (target, name) {
                if (typeof name !== "string") return undefined;
                if (!(name in target)) target[name] = makeObject(name);
                return target[name];
            }
        });
        if (initCallback) initCallback(this);
    };
})();
"""

VIEWPORT_META = '<meta name="viewport" content="width=device-width, initial-scale=1">'

PHONE_CSS_ID = "kioku-phone"
PHONE_CSS = (
    "html { -webkit-text-size-adjust: 100%; }"
    # add-on columns (Mature/Young, progress bars) made the deck list wider
    # than a phone, and the whole page panned sideways: the list scrolls
    # sideways inside its own box instead. It is the containing block of
    # add-on hover tooltips in its cells (Enhance main window), which
    # otherwise made the page 1800px wide; whatever else pokes out by a few
    # px (Review Heatmap's tooltip) is clipped.
    "table:has(.decktd) { display: block; position: relative; width: fit-content; max-width: 100%; box-sizing: border-box; overflow-x: auto; margin: 0 auto; }"
    "html:has(.decktd) { overflow-x: clip; }"
    "@media (max-width: 600px) {"
    "  table:has(.decktd) { padding: 0.5rem; max-width: 100%; }"
    "  table:has(.decktd) .decktd { min-width: 6em; max-width: calc(100vw - 13em); }"
    "  table:has(.decktd) .count { min-width: 2em; }"
    "  table:has(.decktd) td, table:has(.decktd) th { padding-left: 4px !important; padding-right: 4px !important; }"
    "  body:has(.decktd) { margin-left: 0.5em; margin-right: 0.5em; }"
    # add-on buttons in the top bar (right-tray) covered Sync: share one row
    # with the links, or wrap to a second one
    "  .header:has(.tray-item) { display: flex; flex-wrap: wrap; justify-content: center; align-items: start; }"
    "  .header:has(.tray-item) .hitem { padding-left: 6px; padding-right: 6px; }"
    "  .header .tray-item { margin-left: 2px !important; margin-right: 2px !important; }"
    # add-on pop-ups made with tippy.js (AMBOSS: 480-550px wide) ran off the
    # screen, which doesn't scroll sideways
    "  .tippy-popper { max-width: calc(100vw - 16px) !important; }"
    "  .tippy-popper .tippy-tooltip { min-width: 0 !important; max-width: calc(100vw - 16px) !important; }"
    "  .tippy-popper img { max-width: 100%; height: auto; }"
    "}"
    # a tap leaves :hover on the tapped element until the next tap elsewhere,
    # so the top bar's Decks/Add/Browse/Stats kept their hover border
    "@media (hover: none) {"
    "  .header .hitem:hover { border-color: transparent; }"
    "}"
)


def _head_start(html: str) -> int:
    """Where to insert into <head>: after <head>, else after a doctype
    (before it: quirks mode)."""
    tag = re.search(r"<head[^>]*>", html[:4096], re.IGNORECASE) or re.match(
        r"\s*<!doctype[^>]*>", html, re.IGNORECASE
    )
    return tag.end() if tag else 0


def with_viewport(html: str) -> str:
    """Anki's stdHtml pages have no viewport meta. VIEWPORT adds one and
    PHONE_CSS when the document ends, but the page was first drawn at
    980 px, or with desktop column widths, and then jumped: the deck list
    flickered on every refresh (after a sync, on switching screens). In the
    HTML they apply from the first paint."""
    if not re.search(r"<meta[^>]+name=[\"']?viewport", html[:4096], re.IGNORECASE):
        at = _head_start(html)
        html = html[:at] + VIEWPORT_META + html[at:]
    if PHONE_CSS_ID not in html[:8192]:
        # after the page's own style sheets, like VIEWPORT's
        at = html.find("</head>")
        if at < 0:
            at = _head_start(html)
            if html.startswith(VIEWPORT_META, at):
                at += len(VIEWPORT_META)
        html = html[:at] + f'<style id="{PHONE_CSS_ID}">{PHONE_CSS}</style>' + html[at:]
    return html


# Desktop pages have no viewport meta; without one mobile browsers lay them
# out at 980px and shrink them. Also narrows Anki's deck list, the top bar's
# add-on buttons and add-on pop-ups on phones (PHONE_CSS). Pages with both
# in their HTML already (with_viewport) keep them.
VIEWPORT = r"""
(function () {
    if (!document.querySelector("meta[name=viewport]") && document.head) {
        var m = document.createElement("meta");
        m.name = "viewport";
        m.content = "width=device-width, initial-scale=1";
        document.head.appendChild(m);
    }
    if (!document.getElementById("__PHONE_CSS_ID__")) {
        var s = document.createElement("style");
        s.id = "__PHONE_CSS_ID__";
        s.textContent = __PHONE_CSS__;
        (document.head || document.documentElement).appendChild(s);
    }

    // Charts drawn at a fixed size (Review Heatmap: a 636px wide SVG) ran
    // off the screen: wider ones get a viewBox, so they scale down to fit.
    // Charts are redrawn (the heatmap's year buttons), so watch for that.
    var pending = false;
    function fitCharts() {
        pending = false;
        var room = document.documentElement.clientWidth;
        document.querySelectorAll("svg[width][height]").forEach(function (svg) {
            // nested, or scaling already (its own viewBox)
            if (svg.ownerSVGElement) return;
            if (svg.hasAttribute("viewBox") && !svg.dataset.kiokuFit) return;
            var w = parseFloat(svg.getAttribute("width"));
            var h = parseFloat(svg.getAttribute("height"));
            var box = "0 0 " + w + " " + h;
            if (svg.dataset.kiokuFit === box || !(w > room) || !h) return;
            svg.setAttribute("viewBox", box);
            svg.dataset.kiokuFit = box;
            svg.style.maxWidth = "100%";
            svg.style.height = "auto";
        });
    }
    function later() {
        if (!pending) { pending = true; requestAnimationFrame(fitCharts); }
    }
    fitCharts();
    window.addEventListener("resize", later);
    if (document.body) {
        new MutationObserver(later).observe(document.body, {
            childList: true, subtree: true, attributes: true, attributeFilter: ["width"]
        });
    }
})();
"""
VIEWPORT = VIEWPORT.replace("__PHONE_CSS_ID__", PHONE_CSS_ID).replace(
    "__PHONE_CSS__", json.dumps(PHONE_CSS)
)

# Injection times understood by every backend
AT_DOCUMENT_START = 0
AT_DOCUMENT_END = 1
