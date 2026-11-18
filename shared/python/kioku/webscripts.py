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
from string import Template

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

# WebKit (WKWebView, Safari) has no ShadowRoot.getSelection, and
# document.getSelection() reports a selection inside a shadow tree retargeted
# to the shadow host: getRangeAt() gave a collapsed range on the field's host
# and addRange() of a range inside the tree did nothing. Anki's editor keeps
# each field in a shadow root, so underline, bold and the other surround
# buttons left the text as it was (GitHub issue #17). Report the real
# positions (getComposedRanges) and select with setBaseAndExtent, which work.
# WebKit also empties the selection before a field's blur, where Anki saves
# the caret to put it back when the field gets the focus without a tap (Tab,
# back from a dialog): it went to the end of the field. During a field's blur
# the selection reports where it last was in that field.
# Blink has ShadowRoot.getSelection and Anki uses that, so this stays off.
SHADOW_SELECTION = r"""
(function () {
    var proto = window.Selection && Selection.prototype;
    if (!proto || !proto.getComposedRanges || !window.ShadowRoot
            || ShadowRoot.prototype.getSelection || proto.__kiokuShadow) return;
    proto.__kiokuShadow = true;
    function getter(name) {
        return Object.getOwnPropertyDescriptor(proto, name).get;
    }
    var getRangeAt = proto.getRangeAt, addRange = proto.addRange;
    var native = {
        anchorNode: getter("anchorNode"), anchorOffset: getter("anchorOffset"),
        focusNode: getter("focusNode"), focusOffset: getter("focusOffset"),
        isCollapsed: getter("isCollapsed"), rangeCount: getter("rangeCount")
    };
    // the open shadow roots the selection may be in: down from the focused
    // element, and down from the node the retargeted range points at
    function roots(sel) {
        var found = [];
        function down(node) {
            while (node && node.shadowRoot && found.indexOf(node.shadowRoot) < 0) {
                found.push(node.shadowRoot);
                node = node.shadowRoot.activeElement;
            }
        }
        down(document.activeElement);
        if (native.rangeCount.call(sel)) {
            var r = getRangeAt.call(sel, 0);
            down(r.startContainer);
            down(r.startContainer.childNodes[r.startOffset]);
        }
        return found;
    }
    // the real range when the selection is inside a shadow tree, else null
    function composed(sel) {
        if (sel === document.getSelection() && blurring) return blurring;
        return live(sel);
    }
    function live(sel) {
        if (sel !== document.getSelection() || !native.rangeCount.call(sel)) return null;
        var rs = roots(sel);
        if (!rs.length) return null;
        var c;
        try { c = sel.getComposedRanges({shadowRoots: rs}); }
        catch (e) {
            try { c = sel.getComposedRanges.apply(sel, rs); }  // Safari 17
            catch (e2) { return null; }
        }
        c = c && c[0];
        if (!c || !(c.startContainer.getRootNode() instanceof ShadowRoot)) return null;
        return c;
    }
    function backward(sel) {
        return blurring ? blurring.backward : sel.direction === "backward";
    }
    // where the selection last was in each shadow root, and the one reported
    // while a field in that root gets its blur
    var last = new WeakMap(), blurring = null;
    function remember() {
        if (blurring) return;
        var sel = document.getSelection(), c = sel && live(sel);
        if (c) last.set(c.startContainer.getRootNode(), {
            startContainer: c.startContainer, startOffset: c.startOffset,
            endContainer: c.endContainer, endOffset: c.endOffset,
            collapsed: c.collapsed, backward: sel.direction === "backward"
        });
    }
    document.addEventListener("selectionchange", remember);
    window.addEventListener("keydown", remember, true);  // Tab before it moves on
    function done() { blurring = null; }
    window.addEventListener("blur", function (event) {
        var field = event.composedPath()[0];
        if (!field || field === window || !field.getRootNode) return;
        var sel = document.getSelection(), here = sel && live(sel);
        if (here && field.contains(here.startContainer)) return;
        var saved = last.get(field.getRootNode());
        if (!saved || !field.contains(saved.startContainer)
                || !field.contains(saved.endContainer)) return;
        blurring = saved;
        setTimeout(done, 0);
    }, true);
    window.addEventListener("focusout", done);  // after the blur's listeners
    window.addEventListener("focus", done, true);
    proto.getRangeAt = function (index) {
        var c = index === 0 && composed(this);
        if (!c) return getRangeAt.apply(this, arguments);
        var range = document.createRange();
        range.setStart(c.startContainer, c.startOffset);
        range.setEnd(c.endContainer, c.endOffset);
        return range;
    };
    proto.addRange = function (range) {
        if (this === document.getSelection() && range
                && range.startContainer.getRootNode() instanceof ShadowRoot) {
            this.setBaseAndExtent(range.startContainer, range.startOffset,
                                  range.endContainer, range.endOffset);
            return;
        }
        return addRange.apply(this, arguments);
    };
    Object.defineProperty(proto, "rangeCount", {
        configurable: true, enumerable: true,
        get: function () {
            var n = native.rangeCount.call(this);
            return !n && this === document.getSelection() && blurring ? 1 : n;
        }
    });
    function define(name, fromComposed) {
        Object.defineProperty(proto, name, {
            configurable: true, enumerable: true,
            get: function () {
                var c = composed(this);
                return c ? fromComposed(c, backward(this)) : native[name].call(this);
            }
        });
    }
    define("anchorNode", function (c, b) { return b ? c.endContainer : c.startContainer; });
    define("anchorOffset", function (c, b) { return b ? c.endOffset : c.startOffset; });
    define("focusNode", function (c, b) { return b ? c.startContainer : c.endContainer; });
    define("focusOffset", function (c, b) { return b ? c.startOffset : c.endOffset; });
    define("isCollapsed", function (c) { return c.collapsed; });
})();
"""

VIEWPORT_META ='<meta name="viewport" content="width=device-width, initial-scale=1">'

PHONE_CSS_ID = "kioku-phone"
# add-on tables under the deck list (Anki Leaderboard: 7 columns that don't
# wrap) widened the page, which then zoomed out to show them all: they scroll
# sideways in their own box, like the deck list
WIDE_TABLE = "display: block; width: fit-content; max-width: 100%; box-sizing: border-box; overflow-x: auto;"
# the same in add-ons' shadow roots on the deck list page (Anki Leaderboard
# draws its table in one), which PHONE_CSS doesn't reach
SHADOW_CSS = "@media (max-width: 600px) { :host table:not(table table) { %s } }" % WIDE_TABLE
# Rules below pick elements with :has(), which WebViews before Chrome 105
# don't know (Android 11's built-in WebView 87, when its updates are
# removed): they dropped those rules and the deck list ran off the screen.
# There VIEWPORT marks the same elements with classes, and each rule that
# uses $deck_table etc. comes twice: with :has() and with the classes.
_HAS = {
    "deck_table": "table:has(.decktd)",
    "deck_html": "html:has(.decktd)",
    "deck_body": "body:has(.decktd)",
    "other_table": "body:has(.decktd) table:not(:has(.decktd)):not(table:has(.decktd) table)",
    "toolbar_header": ".header:has(> .toolbar)",
    "tray_header": ".header:has(.tray-item)",
}
_MARKED = {
    "deck_table": "table.kioku-decks",
    "deck_html": "html.kioku-decks",
    "deck_body": "html.kioku-decks body",
    "other_table": "table.kioku-wide",
    "toolbar_header": ".header.kioku-toolbar",
    "tray_header": ".header.kioku-tray",
}


def _rule(rule: str) -> str:
    if "$" not in rule:
        return rule
    return Template(rule).substitute(_HAS) + Template(rule).substitute(_MARKED)


PHONE_CSS = "".join(_rule(r) for r in (
    "html { -webkit-text-size-adjust: 100%; }",
    # add-on columns (Mature/Young, progress bars) made the deck list wider
    # than a phone, and the whole page panned sideways: the list scrolls
    # sideways inside its own box instead. It is the containing block of
    # add-on hover tooltips in its cells (Enhance main window), which
    # otherwise made the page 1800px wide; whatever else pokes out by a few
    # px (Review Heatmap's tooltip) is clipped.
    "$deck_table { display: block; position: relative; width: fit-content; max-width: 100%; box-sizing: border-box; overflow-x: auto; margin: 0 auto; }",
    "$deck_html { overflow-x: hidden; overflow-x: clip; }",
    "@media (max-width: 600px) {",
    "  $deck_table { padding: 0.5rem; max-width: 100%; }",
    "  $deck_table .decktd { min-width: 6em; max-width: calc(100vw - 13em); }",
    "  $deck_table .count { min-width: 2em; }",
    "  $deck_table td, $deck_table th { padding-left: 4px !important; padding-right: 4px !important; }",
    "  $deck_body { margin-left: 0.5em; margin-right: 0.5em; }",
    f"  $other_table {{ {WIDE_TABLE} }}",
    # the top bar's links (Decks, Add, Browse, Stats, Sync) didn't wrap and
    # sat in the middle third of a grid: long labels (Russian: Синхронизация)
    # ran off both sides of the screen. Add-on buttons (right-tray) covered
    # Sync. Links and add-on buttons share one row, or wrap to a second one
    "  $toolbar_header { display: flex; flex-wrap: wrap; justify-content: center; align-items: start; }",
    "  .header > .toolbar { white-space: normal; text-wrap: balance; text-align: center; max-width: 100%; }",
    "  .header > .toolbar .hitem { padding-left: 8px; padding-right: 8px; }",
    "  body.fancy .header > .toolbar .hitem:first-child { padding-left: 12px; }",
    "  body.fancy .header > .toolbar .hitem:last-child { padding-right: 12px; }",
    "  $tray_header .hitem { padding-left: 6px; padding-right: 6px; }",
    "  .header .tray-item { margin-left: 2px !important; margin-right: 2px !important; }",
    # add-on pop-ups made with tippy.js (AMBOSS: 480-550px wide) ran off the
    # screen, which doesn't scroll sideways
    "  .tippy-popper { max-width: calc(100vw - 16px) !important; }",
    "  .tippy-popper .tippy-tooltip { min-width: 0 !important; max-width: calc(100vw - 16px) !important; }",
    "  .tippy-popper img { max-width: 100%; height: auto; }",
    "}",
    # a tap leaves :hover on the tapped element until the next tap elsewhere,
    # so the top bar's Decks/Add/Browse/Stats kept their hover border
    "@media (hover: none) {",
    "  .header .hitem:hover { border-color: transparent; }",
    "}",
))


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
    // Shadow roots keep an adopted sheet when an add-on replaces their
    // content (Anki Leaderboard's refresh), unlike a <style> put in them.
    var shadowSheet = null;
    function fitShadowTables() {
        if (!document.adoptedStyleSheets || !document.querySelector(".decktd")) return;
        document.querySelectorAll("*").forEach(function (el) {
            var root = el.shadowRoot;
            if (!root) return;
            if (!shadowSheet) {
                shadowSheet = new CSSStyleSheet();
                shadowSheet.replaceSync(__SHADOW_CSS__);
            }
            if (root.adoptedStyleSheets.indexOf(shadowSheet) < 0) {
                root.adoptedStyleSheets = root.adoptedStyleSheets.concat([shadowSheet]);
            }
        });
    }
    // Without :has() (WebView before Chrome 105) PHONE_CSS finds the deck
    // list, the other tables beside it and the top bar by these classes.
    var hasHas = false;
    try { hasHas = CSS.supports("selector(:has(a))"); } catch (e) {}
    function mark(el, name, on) {
        if (el.classList.contains(name) !== on) el.classList.toggle(name, on);
    }
    function markForOldWebView() {
        if (hasHas) return;
        var decks = !!document.querySelector(".decktd");
        mark(document.documentElement, "kioku-decks", decks);
        document.querySelectorAll("table").forEach(function (table) {
            var deckTable = !!table.querySelector(".decktd");
            mark(table, "kioku-decks", deckTable);
            // document order: tables around this one are marked already
            var parent = table.parentElement;
            mark(table, "kioku-wide", decks && !deckTable &&
                 !(parent && parent.closest("table.kioku-decks")));
        });
        document.querySelectorAll(".header").forEach(function (header) {
            var toolbar = false;
            for (var i = 0; i < header.children.length; i++) {
                if (header.children[i].classList.contains("toolbar")) toolbar = true;
            }
            mark(header, "kioku-toolbar", toolbar);
            mark(header, "kioku-tray", !!header.querySelector(".tray-item"));
        });
    }
    function fit() {
        markForOldWebView();
        fitCharts();
        fitShadowTables();
    }
    function later() {
        if (!pending) { pending = true; requestAnimationFrame(fit); }
    }
    fit();
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
).replace("__SHADOW_CSS__", json.dumps(SHADOW_CSS))

# Injection times understood by every backend
AT_DOCUMENT_START = 0
AT_DOCUMENT_END = 1
