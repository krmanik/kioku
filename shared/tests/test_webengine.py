"""The QtWebEngine stand-in (kioku.webengine) as add-ons use it, over a fake
platform web view. The AMBOSS add-on is the model: a named profile subclass
with a parent keyword, cookies set from Python, and page history."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDateTime, QObject, QUrl
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWidgets import QApplication

from kioku import webengine, webscripts

app = QApplication.instance() or QApplication([])


class AddonProfile(webengine.QWebEngineProfile):
    def __init__(self, storage_name: str, parent: QObject | None = None) -> None:
        super().__init__(storage_name, parent=parent)
        self.added: list[str] = []
        self.cookieStore().cookieAdded.connect(
            lambda c: self.added.append(bytes(c.name()).decode())
        )


def auth_cookie() -> QNetworkCookie:
    cookie = QNetworkCookie(b"token", b"secret")
    cookie.setDomain(".example.com")
    cookie.setPath("/")
    cookie.setSecure(True)
    cookie.setHttpOnly(True)
    cookie.setExpirationDate(QDateTime.fromSecsSinceEpoch(2_000_000_000))
    return cookie


def test_named_profile_with_parent_keyword(platform) -> None:
    owner = QObject()
    profile = AddonProfile("amboss", parent=owner)
    assert profile.parent() is owner
    assert profile.storageName() == "amboss"
    assert not profile.isOffTheRecord()
    assert webengine.QWebEngineProfile.defaultProfile().isOffTheRecord()


def test_cookies_reach_the_platform(platform) -> None:
    profile = AddonProfile("amboss")
    store = profile.cookieStore()
    store.setCookie(auth_cookie())
    assert profile.added == ["token"]
    kind, url, header = platform.cookie_calls[-1]
    assert (kind, url) == ("set", "https://example.com/")
    assert header.startswith("token=secret;")
    assert "HttpOnly" in header and "secure" in header.lower()
    assert "domain=.example.com" in header

    store.loadAllCookies()
    assert profile.added == ["token", "token"]

    store.deleteAllCookies()
    assert platform.cookie_calls[-1] == ("delete", ".example.com", None)
    store.loadAllCookies()
    assert profile.added == ["token", "token"]


def test_cookie_without_domain_takes_the_origin(platform) -> None:
    store = AddonProfile("x").cookieStore()
    store.setCookie(QNetworkCookie(b"a", b"1"), QUrl("https://site.test/page"))
    assert platform.cookie_calls[-1][:2] == ("set", "https://site.test/page")
    assert "domain=site.test" in platform.cookie_calls[-1][2]


def test_page_with_profile_and_history(platform) -> None:
    profile = AddonProfile("amboss")
    parent = QObject()
    page = webengine.QWebEnginePage(profile, parent)
    assert page.profile() is profile and page.parent() is parent
    page2 = webengine.QWebEnginePage(profile=profile, parent=parent)
    assert page2.profile() is profile and page2.parent() is parent

    history = page.history()
    assert not history.canGoBack()
    assert not history.backItem().url().toString()
    page._web.state = {"back": "https://a.test/1", "forward": ""}
    assert history.canGoBack() and not history.canGoForward()
    assert history.backItem().url().toString() == "https://a.test/1"
    history.back()
    assert page._web.calls[-1] == "back"


def test_set_html_has_viewport_from_the_start() -> None:
    # Anki's stdHtml page: the meta right after <head>, the phone CSS after
    # the page's own style sheets
    page = (
        "<!doctype html>\n<html><head><title>x</title>"
        "<link rel=stylesheet href=deckbrowser.css></head><body></body></html>"
    )
    out = webscripts.with_viewport(page)
    assert out.startswith("<!doctype html>")
    assert out.index("<head>") < out.index('name="viewport"') < out.index("<title>")
    assert out.index("deckbrowser.css") < out.index('id="kioku-phone"') < out.index("</head>")
    assert webscripts.with_viewport(out) == out
    # a fragment without <head>: after the doctype, never before it
    out = webscripts.with_viewport("<!DOCTYPE html><p>hi</p>")
    assert out.startswith("<!DOCTYPE html><meta")
    assert webscripts.with_viewport("<p>hi</p>").startswith("<meta")
    # a page with its own viewport keeps it
    own = "<head><meta name=viewport content='width=500'></head>"
    out = webscripts.with_viewport(own)
    assert out.count("viewport") == 1 and 'id="kioku-phone"' in out


def test_url_changes_when_the_new_page_is_there(platform) -> None:
    # the Incremento add-on loads its reader only when url() isn't the reader's
    # yet, and otherwise talks to the page right away
    page = webengine.QWebEnginePage()
    platform_url = {"url": "file:///old.html"}
    page._web.url = lambda: platform_url["url"]
    page._web.title = lambda: ""
    # the platform views report the requested URL as soon as a load starts
    page._web.load_url = lambda url, headers: platform_url.update(url=url)
    changed: list[str] = []
    page.urlChanged.connect(lambda url: changed.append(url.toString()))

    page.load(QUrl("file:///new.html"))
    assert page.url().toString() == "file:///old.html"
    assert page.requestedUrl().toString() == "file:///new.html"
    assert changed == []

    page._on_load_finished(True)
    assert page.url().toString() == "file:///new.html"
    assert page.requestedUrl().toString() == "file:///new.html"
    assert changed == ["file:///new.html"]
