"""The iOS web view backend: WKWebView, driven through rubicon-objc.

One WebView wraps one WKWebView plus its configuration. Everything Qt-shaped
(QUrl, signals, QWebEngine* semantics) lives in kioku.webengine; this module
only speaks Objective-C and plain Python values.
"""

from __future__ import annotations

import json
import logging
import os
import weakref
from ctypes import c_bool, c_long, c_void_p
from typing import Any, Callable

from rubicon.objc import (
    Block,
    CGPoint,
    CGRect,
    CGSize,
    NSObject,
    ObjCBlock,
    ObjCClass,
    ObjCInstance,
    SEL,
    at,
    objc_method,
    py_from_ns,
)
from rubicon.objc.api import ObjCBoundMethod
from rubicon.objc.runtime import load_library, objc_id

load_library("WebKit")
load_library("UIKit")

logger = logging.getLogger("kioku.wk")

WKWebView = ObjCClass("WKWebView")
WKWebViewConfiguration = ObjCClass("WKWebViewConfiguration")
WKUserScript = ObjCClass("WKUserScript")
WKContentWorld = ObjCClass("WKContentWorld")
NSURL = ObjCClass("NSURL")
NSMutableURLRequest = ObjCClass("NSMutableURLRequest")
NSNumber = ObjCClass("NSNumber")
UIColor = ObjCClass("UIColor")
NSData = ObjCClass("NSData")
NSDictionary = ObjCClass("NSDictionary")
NSValue = ObjCClass("NSValue")
UIPrintPageRenderer = ObjCClass("UIPrintPageRenderer")
UIGraphicsPDFRenderer = ObjCClass("UIGraphicsPDFRenderer")
WKWebsiteDataStore = ObjCClass("WKWebsiteDataStore")
NSHTTPCookie = ObjCClass("NSHTTPCookie")

# WKUserScriptInjectionTime; the same values as kioku.webscripts
AT_DOCUMENT_START = 0
AT_DOCUMENT_END = 1
POLICY_CANCEL = 0
POLICY_ALLOW = 1
FLEXIBLE_SIZE = 2 | 16  # UIViewAutoresizingFlexibleWidth | FlexibleHeight
NO_INSET_ADJUSTMENT = 2  # UIScrollViewContentInsetAdjustmentNever
A4 = (595.2, 841.8)  # points
PDF_MARGIN = 36.0

CHANNEL_HANDLER = "kiokuChannel"
CONSOLE_HANDLER = "kiokuConsole"
SELECTION_HANDLER = "kiokuSelection"

def prop(obj: Any, name: str) -> Any:
    """Read an Objective-C property. Rubicon only treats a name as a property
    when the runtime declares one, so plain getters come back as methods."""
    value = getattr(obj, name)
    if isinstance(value, ObjCBoundMethod):
        value = value()
    return value


def same(a: Any, b: Any) -> bool:
    return a is not None and b is not None and a.ptr.value == b.ptr.value


def block(ptr: int | None, *argtypes: Any) -> ObjCBlock:
    """Wrap a block WebKit passed us; its blocks carry no type signature."""
    return ObjCBlock(objc_id(ptr), None, *argtypes)


# Cookies ---------------------------------------------------------------------
# Every WKWebView uses the default data store, so all pages share one jar.

_cookie_blocks: set[Any] = set()


def _cookie_store() -> Any:
    return prop(prop(WKWebsiteDataStore, "defaultDataStore"), "httpCookieStore")


def _domain_matches(cookie_domain: str, domain: str) -> bool:
    a, b = cookie_domain.lstrip(".").lower(), domain.lstrip(".").lower()
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def set_cookie(url: str, header: str) -> None:
    """Store a cookie given in Set-Cookie form for url."""
    nsurl = NSURL.URLWithString_(at(url))
    fields = NSDictionary.dictionaryWithObject_forKey_(at(header), at("Set-Cookie"))
    cookies = NSHTTPCookie.cookiesWithResponseHeaderFields_forURL_(fields, nsurl)
    store = _cookie_store()
    for cookie in cookies:
        store.setCookie_completionHandler_(cookie, None)


def delete_cookies(domain: str, name: str | None) -> None:
    """Delete the cookies on domain (and its subdomains), or only `name`."""
    store = _cookie_store()
    holder: list[Any] = []

    def got(array: objc_id) -> None:
        _cookie_blocks.discard(holder[0])
        for cookie in ObjCInstance(array):
            if not _domain_matches(str(prop(cookie, "domain")), domain):
                continue
            if name is None or str(prop(cookie, "name")) == name:
                store.deleteCookie_completionHandler_(cookie, None)

    blk = Block(got, None, objc_id)
    holder.append(blk)
    _cookie_blocks.add(blk)
    store.getAllCookies_(blk)


# WKWebView instances keyed by pointer, so the shared ObjC delegates can find
# the Python object that owns the view.
_views: "weakref.WeakValueDictionary[int, WebView]" = weakref.WeakValueDictionary()


def _owner(webview: Any) -> WebView | None:
    if webview is None:
        return None
    return _views.get(webview.ptr.value)


def _view_for_controller(controller: Any) -> WebView | None:
    for view in list(_views.values()):
        if same(view.controller, controller):
            return view
    return None


def _url_string(request: Any) -> str:
    url = prop(request, "URL")
    return str(prop(url, "absoluteString")) if url is not None else ""


class KiokuScriptHandler(NSObject):
    @objc_method
    def userContentController_didReceiveScriptMessage_(
        self, controller, message
    ) -> None:
        view = _view_for_controller(controller)
        if view is None:
            return
        name = str(prop(message, "name"))
        body = prop(message, "body")
        text = str(body) if body is not None else ""
        try:
            if name == CONSOLE_HANDLER:
                view.on_console(json.loads(text))
            elif name == SELECTION_HANDLER:
                view.on_selection(text)
        except Exception:
            logger.exception("script message %s", name)

    @objc_method
    def userContentController_didReceiveScriptMessage_replyHandler_(
        self, controller, message, reply: c_void_p
    ) -> None:
        # void (^)(id reply, NSString *errorMessage)
        reply_block = block(reply, objc_id, objc_id)
        view = _view_for_controller(controller)
        try:
            if view is None:
                raise RuntimeError("no view for message")
            call = json.loads(str(prop(message, "body")))
            result = view.on_channel_call(
                call["obj"], call["method"], call.get("args", [])
            )
            reply_block(at(json.dumps(result)), None)
        except Exception as e:
            logger.exception("channel call failed")
            reply_block(None, at(str(e)))


class KiokuNavigationDelegate(NSObject):
    @objc_method
    def webView_decidePolicyForNavigationAction_decisionHandler_(
        self, webview, action, handler: c_void_p
    ) -> None:
        # void (^)(WKNavigationActionPolicy)
        decide = block(handler, c_long)
        view = _owner(webview)
        allow = True
        try:
            if view is not None:
                url = _url_string(prop(action, "request"))
                frame = prop(action, "targetFrame")
                main_frame = frame is None or bool(prop(frame, "isMainFrame"))
                nav_type = int(prop(action, "navigationType"))
                allow = view.on_navigation(url, nav_type, main_frame)
        except Exception:
            logger.exception("navigation policy")
        decide(POLICY_ALLOW if allow else POLICY_CANCEL)

    @objc_method
    def webView_didStartProvisionalNavigation_(self, webview, navigation) -> None:
        view = _owner(webview)
        if view is not None:
            view.on_load_started()

    @objc_method
    def webView_didFinishNavigation_(self, webview, navigation) -> None:
        view = _owner(webview)
        if view is not None:
            view.on_load_finished(True)

    @objc_method
    def webView_didFailNavigation_withError_(self, webview, navigation, error) -> None:
        view = _owner(webview)
        if view is not None:
            logger.warning("navigation failed: %s", prop(error, "localizedDescription"))
            view.on_load_finished(False)

    @objc_method
    def webView_didFailProvisionalNavigation_withError_(
        self, webview, navigation, error
    ) -> None:
        view = _owner(webview)
        if view is not None:
            logger.warning(
                "provisional navigation failed: %s", prop(error, "localizedDescription")
            )
            view.on_load_finished(False)

    @objc_method
    def webViewWebContentProcessDidTerminate_(self, webview) -> None:
        logger.warning("web content process terminated; reloading")
        webview.reload()


class KiokuUIDelegate(NSObject):
    @objc_method
    def webView_runJavaScriptAlertPanelWithMessage_initiatedByFrame_completionHandler_(
        self, webview, message, frame, handler: c_void_p
    ) -> None:
        block(handler)()
        view = _owner(webview)
        if view is not None:
            view.on_alert(str(message))

    @objc_method
    def webView_runJavaScriptConfirmPanelWithMessage_initiatedByFrame_completionHandler_(
        self, webview, message, frame, handler: c_void_p
    ) -> None:
        done = block(handler, c_bool)
        view = _owner(webview)
        ok = False
        try:
            if view is not None:
                ok = bool(view.on_confirm(str(message)))
        finally:
            done(ok)

    @objc_method
    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
        self, webview, configuration, action, features
    ) -> objc_id:
        # target=_blank: let the page decide whether to open it externally
        view = _owner(webview)
        if view is not None:
            view.on_navigation(_url_string(prop(action, "request")), 0, True)
        return None


_script_handler = KiokuScriptHandler.alloc().init()
_navigation_delegate = KiokuNavigationDelegate.alloc().init()
_ui_delegate = KiokuUIDelegate.alloc().init()


class WebView:
    """Owns one WKWebView. Callbacks are overridden by kioku.webengine."""

    # defines window.__kiokuNative for kioku.webscripts.PRELUDE
    BRIDGE = (
        "window.__kiokuNative = {"
        "send: function (name, text) {"
        " var h = {console: 'kiokuConsole', selection: 'kiokuSelection'}[name];"
        " window.webkit.messageHandlers[h].postMessage(text); },"
        "call: function (text) {"
        " return window.webkit.messageHandlers.kiokuChannel.postMessage(text); }"
        "};"
    )

    @staticmethod
    def prepare_host(widget: Any) -> None:
        """A native child window gives the widget a UIView for the WKWebView."""
        from PyQt6.QtCore import Qt

        widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)

    def __init__(self) -> None:
        config = WKWebViewConfiguration.alloc().init()
        config.setAllowsInlineMediaPlayback_(True)
        config.setMediaTypesRequiringUserActionForPlayback_(0)
        # like QtWebEngine (LocalContentCanAccessFileUrls): local pages may
        # read other local files, e.g. an add-on's pdf.js reading a PDF
        prop(config, "preferences").setValue_forKey_(
            NSNumber.numberWithBool_(True), at("allowFileAccessFromFileURLs")
        )
        self.controller = prop(config, "userContentController")
        page_world = prop(WKContentWorld, "pageWorld")
        self.controller.addScriptMessageHandlerWithReply_contentWorld_name_(
            _script_handler, page_world, at(CHANNEL_HANDLER)
        )
        self.controller.addScriptMessageHandler_name_(
            _script_handler, at(CONSOLE_HANDLER)
        )
        self.controller.addScriptMessageHandler_name_(
            _script_handler, at(SELECTION_HANDLER)
        )
        webview = WKWebView.alloc().initWithFrame_configuration_(
            CGRect(CGPoint(0, 0), CGSize(100, 100)), config
        )
        webview.setNavigationDelegate_(_navigation_delegate)
        webview.setUIDelegate_(_ui_delegate)
        webview.setAutoresizingMask_(FLEXIBLE_SIZE)
        webview.setAllowsLinkPreview_(False)
        scroll = prop(webview, "scrollView")
        # pinching out shrank the page into a dark frame that sprang back
        scroll.setBouncesZoom_(False)
        # the bottom bar reaches into the home indicator's area and pads its
        # page itself (kioku.screenedges); left to UIKit, the page was inset
        # again and a band of the view's background showed under it
        scroll.setContentInsetAdjustmentBehavior_(NO_INSET_ADJUSTMENT)
        if webview.respondsToSelector_(SEL("setInspectable:")):
            webview.setInspectable_(True)  # Safari Web Inspector
        self.webview = webview
        self._pending: set[Any] = set()
        _views[webview.ptr.value] = self

    # Scripts ---------------------------------------------------------------

    def set_user_scripts(self, scripts: list[tuple[str, int, bool]]) -> None:
        """scripts: (source, injection time, main frame only)"""
        self.controller.removeAllUserScripts()
        for source, when, main_only in scripts:
            script = WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
                at(source), when, main_only
            )
            self.controller.addUserScript_(script)

    # Loading ---------------------------------------------------------------

    def load_url(self, url: str, headers: dict[str, str] | None = None) -> None:
        nsurl = NSURL.URLWithString_(at(url))
        if nsurl is None:
            logger.warning("bad url %s", url)
            return
        if prop(nsurl, "isFileURL"):
            # loadRequest lets a local page read only itself
            home = NSURL.fileURLWithPath_isDirectory_(at(os.path.expanduser("~")), True)
            self.webview.loadFileURL_allowingReadAccessToURL_(nsurl, home)
            return
        request = NSMutableURLRequest.requestWithURL_(nsurl)
        for key, value in (headers or {}).items():
            request.setValue_forHTTPHeaderField_(at(value), at(key))
        self.webview.loadRequest_(request)

    def load_html(self, html: str, base_url: str | None) -> None:
        base = NSURL.URLWithString_(at(base_url)) if base_url else None
        self.webview.loadHTMLString_baseURL_(at(html), base)

    def reload(self) -> None:
        self.webview.reload()

    def stop(self) -> None:
        self.webview.stopLoading()

    def back(self) -> None:
        self.webview.goBack()

    def forward(self) -> None:
        self.webview.goForward()

    def url(self) -> str:
        u = prop(self.webview, "URL")
        return str(prop(u, "absoluteString")) if u is not None else ""

    def title(self) -> str:
        t = prop(self.webview, "title")
        return str(t) if t is not None else ""

    def history(self) -> dict[str, str]:
        """URLs of the back and forward items ("" when there is none)."""
        items = prop(self.webview, "backForwardList")
        state = {}
        for key, item in (("back", prop(items, "backItem")), ("forward", prop(items, "forwardItem"))):
            u = prop(item, "URL") if item is not None else None
            state[key] = str(prop(u, "absoluteString")) if u is not None else ""
        return state

    # JavaScript --------------------------------------------------------------

    def evaluate(self, js: str, callback: Callable[[Any], None] | None) -> None:
        holder: list[Any] = []

        def done(result: objc_id, error: objc_id) -> None:
            self._pending.discard(holder[0])
            value = None
            if result:
                try:
                    value = py_from_ns(ObjCInstance(result))
                except Exception:
                    value = None
            if callback is not None:
                try:
                    callback(value)
                except Exception:
                    logger.exception("runJavaScript callback")

        blk = Block(done, None, objc_id, objc_id)
        holder.append(blk)
        self._pending.add(blk)
        self.webview.evaluateJavaScript_completionHandler_(at(js), blk)

    def print_pdf(self, path: str) -> None:
        """Write the page to an A4 PDF file; on_pdf_finished() reports the
        result."""
        ok = False
        try:
            renderer = UIPrintPageRenderer.alloc().init()
            renderer.addPrintFormatter_startingAtPageAtIndex_(
                prop(self.webview, "viewPrintFormatter"), 0
            )
            paper = CGRect(CGPoint(0, 0), CGSize(*A4))
            printable = CGRect(
                CGPoint(PDF_MARGIN, PDF_MARGIN),
                CGSize(A4[0] - 2 * PDF_MARGIN, A4[1] - 2 * PDF_MARGIN),
            )
            # read-only properties, meant to be overridden; KVC sets them
            renderer.setValue_forKey_(NSValue.valueWithCGRect_(paper), at("paperRect"))
            renderer.setValue_forKey_(
                NSValue.valueWithCGRect_(printable), at("printableRect")
            )
            pages = int(prop(renderer, "numberOfPages"))

            def draw(context: objc_id) -> None:
                for i in range(pages):
                    ObjCInstance(context).beginPage()
                    renderer.drawPageAtIndex_inRect_(i, paper)

            pdf = UIGraphicsPDFRenderer.alloc().initWithBounds_(paper)
            data = pdf.PDFDataWithActions_(Block(draw, None, objc_id))
            ok = bool(data.writeToFile_atomically_(at(path), True))
        except Exception:
            logger.exception("print to PDF")
        self.on_pdf_finished(path, ok)

    # Appearance --------------------------------------------------------------

    def set_background(self, r: float, g: float, b: float, a: float) -> None:
        color = UIColor.colorWithRed_green_blue_alpha_(r, g, b, a)
        self.webview.setOpaque_(a >= 1.0)
        self.webview.setBackgroundColor_(color)
        prop(self.webview, "scrollView").setBackgroundColor_(color)
        if self.webview.respondsToSelector_(SEL("setUnderPageBackgroundColor:")):
            self.webview.setUnderPageBackgroundColor_(color)

    def set_zoom(self, factor: float) -> None:
        if self.webview.respondsToSelector_(SEL("setPageZoom:")):
            self.webview.setPageZoom_(factor)

    # Hosting ---------------------------------------------------------------

    def attach(self, widget: Any) -> None:
        """Put the web view into the widget's UIView (its winId)."""
        host = ObjCInstance(c_void_p(int(widget.winId())))
        current = prop(self.webview, "superview")
        if current is not None:
            if same(current, host):
                return
            self.webview.removeFromSuperview()
        self.webview.setFrame_(prop(host, "bounds"))
        host.addSubview_(self.webview)

    def detach(self) -> None:
        self.webview.removeFromSuperview()

    def close(self) -> None:
        self.detach()
        _views.pop(self.webview.ptr.value, None)
        self.controller.removeAllScriptMessageHandlers()

    # Callbacks, overridden by the owner -------------------------------------

    def on_console(self, entry: dict) -> None: ...
    def on_selection(self, text: str) -> None: ...
    def on_channel_call(self, obj: str, method: str, args: list) -> Any: ...
    def on_navigation(self, url: str, nav_type: int, main_frame: bool) -> bool:
        return True
    def on_load_started(self) -> None: ...
    def on_load_finished(self, ok: bool) -> None: ...
    def on_alert(self, text: str) -> None: ...
    def on_pdf_finished(self, path: str, ok: bool) -> None: ...
    def on_confirm(self, text: str) -> bool:
        return False
