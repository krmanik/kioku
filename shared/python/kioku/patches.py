"""The places where Anki desktop assumes a desktop OS, adjusted for phones.

On iOS sys.platform is "ios" and on Android "android", so Anki takes its
Linux code paths. Most of them work unchanged; the ones below would load
libraries or start processes that do not exist here. What differs between
the platforms comes from kioku_platform.
"""

from __future__ import annotations

import logging
import os
import types

import kioku_platform as platform

logger = logging.getLogger("kioku.patches")

# Where Anki's update prompts send the user
KIOKU_RELEASES = "https://github.com/krmanik/kioku/releases/latest"


def apply() -> None:
    import aqt
    import aqt.theme
    import aqt.utils

    # setupGL() loads libGL.so.1 and configures Qt WebEngine's renderer;
    # neither exists here. (Its arguments change between releases: 26.09 added
    # the video driver.)
    aqt.setupGL = lambda *args, **kwargs: None

    # Linux dark mode detection runs dbus-send/gsettings
    aqt.theme.get_linux_dark_mode = _dark_mode

    # Other modules import these by name, so replace the code in place.
    aqt.utils.openFolder.__code__ = _open_folder.__code__
    aqt.utils.show_in_folder.__code__ = _show_in_folder.__code__
    # Desktop file dialogs return paths the app may not read (iOS) or
    # content:// URIs (Android); the platform pickers copy into the app.
    aqt.utils.getFile.__code__ = _get_file.__code__
    aqt.utils.getSaveFile.__code__ = _get_save_file.__code__
    # Taps go to the native web views, so Qt often has no focus widget (or
    # one in a window that has closed); Anki then takes changes made on the
    # main screen (e.g. collapsing a deck) for changes from another window,
    # dims the main screen and waits for a focus change to undo it.
    aqt.utils.current_window.__code__ = _current_window.__code__
    # Qt sizes a window to at most 2/3 of the screen, which cut tooltips
    # longer than that off on a phone
    aqt.utils._kioku_tooltip = types.FunctionType(
        aqt.utils.tooltip.__code__,
        aqt.utils.__dict__,
        "tooltip",
        aqt.utils.tooltip.__defaults__,
    )
    aqt.utils._kioku_fit_tooltip = _fit_tooltip
    aqt.utils.tooltip.__code__ = _tooltip.__code__

    _patch_app()
    _patch_audio()
    _patch_profile_saving()
    _patch_ui_scale()
    _patch_bar_heights()
    _patch_review_menu()
    _patch_full_screen()
    _patch_screen_edges()
    _patch_splitters()
    _patch_docks()
    _patch_update_check()
    _patch_page_html()
    _python_313_compat()
    _addon_platform()


def _dark_mode() -> bool:
    try:
        return platform.dark_mode()
    except Exception:
        logger.exception("dark mode detection")
        return False


def _open_folder(path: str) -> None:
    import kioku_platform

    kioku_platform.open_folder(path)


def _show_in_folder(path: str) -> None:
    import os

    import kioku_platform

    kioku_platform.open_folder(path if os.path.isdir(path) else os.path.dirname(path))


def _current_window():  # type: ignore[no-untyped-def]
    import aqt
    from aqt.qt import QApplication

    widget = QApplication.focusWidget()
    window = widget.window() if widget is not None else None
    if window is None or not window.isVisible():
        window = QApplication.activeModalWidget() or QApplication.activeWindow()
    if window is None or not window.isVisible():
        window = aqt.mw
    return window


def _get_file(parent, title, cb, filter="*", dir=None, key=None, multi=False):  # type: ignore[no-untyped-def]
    import kioku_platform

    paths = kioku_platform.pick_files(filter, multi)
    if not paths:
        return None
    result = paths if multi else paths[0]
    if cb:
        cb(result)
    return result


def _get_save_file(parent, title, dir_description, key, ext, fname=""):  # type: ignore[no-untyped-def]
    import os

    import kioku_platform
    from aqt.utils import askUser, tr

    name = fname or f"export{ext}"
    if not name.lower().endswith(ext):
        name += ext
    path = kioku_platform.save_path(name)
    if os.path.exists(path) and not askUser(
        tr.qt_misc_this_file_exists_are_you_sure(), parent
    ):
        return None
    return path


def _tooltip(msg, period=3000, parent=None, x_offset=0, y_offset=100):  # type: ignore[no-untyped-def]
    # runs as aqt.utils.tooltip, with aqt.utils' globals
    _kioku_tooltip(msg, period, parent, x_offset, y_offset)  # type: ignore[name-defined]  # noqa: F821
    _kioku_fit_tooltip(_tooltipLabel)  # type: ignore[name-defined]  # noqa: F821


def _fit_tooltip(label) -> None:  # type: ignore[no-untyped-def]
    """Full width up to the screen's, wrapped beyond it, kept on the screen."""
    if label is None or label.screen() is None:
        return
    screen = label.screen().availableGeometry()
    width = min(label.sizeHint().width(), screen.width() - 16)
    if width < label.sizeHint().width():
        label.setWordWrap(True)
    label.resize(width, label.heightForWidth(width) if label.wordWrap() else label.sizeHint().height())
    x = min(max(label.x(), screen.left() + 8), screen.left() + screen.width() - 8 - width)
    label.move(x, label.y())


def _patch_app() -> None:
    import aqt

    import sys

    from kioku import advanced, ankidroid, ankiwebsync, devtools, mediaserver, packs, syncserver, windows

    advanced.install()
    packs.install()
    if sys.platform == "android":
        ankidroid.install()
        ankiwebsync.install()
    original_init = aqt.AnkiApp.__init__

    def init(self, argv):  # type: ignore[no-untyped-def]
        original_init(self, argv)
        _fix_highlighted_text(self)
        windows.install(self)
        mediaserver.install()
        syncserver.install()
        devtools.install()

    aqt.AnkiApp.__init__ = init


def _fix_highlighted_text(app) -> None:  # type: ignore[no-untyped-def]
    """Until a profile loads, Anki's palette is not applied and Qt's own is
    used. On Android in dark mode, that one has light text on a light
    highlight, so the selected row of the first-run language list was
    blank. Such text becomes black or white, whichever reads on it."""
    from aqt.qt import QColor, QPalette

    def luminance(color: QColor) -> float:
        return 0.2126 * color.redF() + 0.7152 * color.greenF() + 0.0722 * color.blueF()

    def fix() -> None:
        palette = app.palette()
        role = QPalette.ColorRole
        # Anki's highlight is half transparent, over the list's background
        highlight = palette.color(role.Highlight)
        alpha = highlight.alphaF()
        background = alpha * luminance(highlight) + (1 - alpha) * luminance(
            palette.color(role.Base)
        )
        if abs(background - luminance(palette.color(role.HighlightedText))) >= 0.4:
            return
        dark = background > 0.5
        palette.setColor(role.HighlightedText, QColor("black" if dark else "white"))
        app.setPalette(palette)

    fix()
    # the system's dark mode can change before then
    app.paletteChanged.connect(lambda _palette: fix())


def _patch_profile_saving() -> None:
    """Anki writes the profile (AnkiWeb login, preferences) to prefs21.db
    only when the profile is closed or Anki quits. Phone apps are usually
    killed in the background instead, which lost the AnkiWeb login after
    every restart. Save it when the login changes and whenever the app
    leaves the foreground."""
    import aqt
    from aqt.profiles import ProfileManager
    from aqt.qt import Qt

    def saving(setter):  # type: ignore[no-untyped-def]
        def set_and_save(self, val):  # type: ignore[no-untyped-def]
            setter(self, val)
            _save_profile(self)

        return set_and_save

    for name in ("set_sync_key", "set_sync_username", "set_host_number", "set_current_sync_url"):
        setattr(ProfileManager, name, saving(getattr(ProfileManager, name)))

    original_init = aqt.AnkiApp.__init__

    def init(self, argv):  # type: ignore[no-untyped-def]
        original_init(self, argv)

        def on_state(state: Qt.ApplicationState) -> None:
            if state != Qt.ApplicationState.ApplicationActive and aqt.mw is not None:
                _save_profile(aqt.mw.pm)

        self.applicationStateChanged.connect(on_state)

    aqt.AnkiApp.__init__ = init


# Preferences › Appearance › User interface size, in percent: phones also
# allow smaller than Anki's 100%
UI_SCALE_MIN, UI_SCALE_MAX = 50, 200


def _patch_ui_scale() -> None:
    """Anki sets QT_SCALE_FACTOR from the user interface size only after
    creating the QApplication, when Qt no longer reads it, so the setting
    did nothing. Set it as soon as the global settings are loaded, before
    the QApplication. The web views draw their pages themselves: they get
    the size as their zoom (kioku.webengine)."""
    import os

    from aqt.preferences import Preferences
    from aqt.profiles import ProfileManager

    from . import webengine

    def ui_scale(self) -> float:  # type: ignore[no-untyped-def]
        scale = self.meta.get("uiScale", 1.0)
        return min(max(scale, UI_SCALE_MIN / 100), UI_SCALE_MAX / 100)

    ProfileManager.uiScale = ui_scale

    setup_meta = ProfileManager.setupMeta

    def setup_meta_and_scale(self):  # type: ignore[no-untyped-def]
        result = setup_meta(self)
        scale = self.uiScale()
        os.environ["QT_SCALE_FACTOR"] = str(scale)
        webengine.UI_SCALE = scale
        return result

    ProfileManager.setupMeta = setup_meta_and_scale

    setup_global = Preferences.setup_global

    def setup_global_range(self):  # type: ignore[no-untyped-def]
        self.form.uiScale.setRange(UI_SCALE_MIN, UI_SCALE_MAX)
        setup_global(self)

    Preferences.setup_global = setup_global_range


def _save_profile(pm) -> None:  # type: ignore[no-untyped-def]
    if getattr(pm, "profile", None) is None or getattr(pm, "name", None) is None:
        return
    try:
        pm.save()
    except Exception:
        logger.exception("saving the profile")


def _patch_bar_heights() -> None:
    """The top and bottom bars size themselves from their page's height.
    When that measurement runs while the page is still loading (seen at
    start-up while an add-on's dialog was open), it comes back empty; Anki
    then only resets the main screen, and the top bar stayed half the
    screen tall. Measure again until the bar has a fixed height."""
    import aqt.toolbar  # noqa: F401  (its web views override adjustHeightToFit)
    from aqt.qt import QTimer, QWIDGETSIZE_MAX, sip
    from aqt.webview import AnkiWebView

    def unsized(web: AnkiWebView) -> bool:
        return not sip.isdeleted(web) and web.maximumHeight() >= QWIDGETSIZE_MAX

    def retry(web: AnkiWebView) -> None:
        tries = getattr(web, "_kioku_height_tries", 0)
        if tries < 5 and unsized(web):
            web._kioku_height_tries = tries + 1
            # the view's own method: the top bar's clears a min-height first,
            # without which it measures the main screen's height
            web._kioku_retrying = True
            try:
                web.adjustHeightToFit()
            finally:
                web._kioku_retrying = False
            QTimer.singleShot(2000, lambda: retry(web))

    def watched(adjust):  # type: ignore[no-untyped-def]
        def adjust_height_to_fit(self):  # type: ignore[no-untyped-def]
            if getattr(self, "_kioku_adjusting", False):
                # a subclass calling super()
                return adjust(self)
            if not getattr(self, "_kioku_retrying", False):
                self._kioku_height_tries = 0
                QTimer.singleShot(2000, lambda: retry(self))
            self._kioku_adjusting = True
            try:
                return adjust(self)
            finally:
                self._kioku_adjusting = False

        return adjust_height_to_fit

    def subclasses(cls: type) -> list[type]:
        return [cls] + [s for c in cls.__subclasses__() for s in subclasses(c)]

    for cls in subclasses(AnkiWebView):
        if "adjustHeightToFit" in cls.__dict__:
            cls.adjustHeightToFit = watched(cls.__dict__["adjustHeightToFit"])

    original_on_height = AnkiWebView._onHeight

    def on_height(self, qvar):  # type: ignore[no-untyped-def]
        if qvar is None:
            QTimer.singleShot(300, lambda: retry(self))
            return
        original_on_height(self, qvar)

    AnkiWebView._onHeight = on_height


def _patch_review_menu() -> None:
    """The review screen's Edit and More buttons are hidden below 583 px
    (reviewer-bottom.css), which leaves a phone without them: desktop users
    press E and M instead. Offer both in the Edit menu while reviewing."""
    import aqt
    from aqt import gui_hooks
    from aqt.qt import QAction, QMenu, Qt, qconnect
    from aqt.utils import tr

    def inert(menu: QMenu) -> None:
        # Anki's menu rows carry shortcuts the reviewer already handles; as
        # window shortcuts in the menu bar they would make those ambiguous
        for action in menu.actions():
            action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
            if action.menu() is not None:
                inert(action.menu())

    def setup(mw) -> None:  # type: ignore[no-untyped-def]
        menu = mw.form.menuEdit
        separator = menu.addSeparator()
        edit = QAction(tr.editing_edit_current(), mw)
        qconnect(edit.triggered, lambda: mw.onEditCurrent())
        menu.addAction(edit)
        more = menu.addMenu(tr.studying_more())

        def fill_more() -> None:
            more.clear()
            reviewer = mw.reviewer
            reviewer._addMenuItems(more, reviewer._contextMenu())
            gui_hooks.reviewer_will_show_context_menu(reviewer, more)
            inert(more)

        def update() -> None:
            reviewing = mw.state == "review" and mw.reviewer.card is not None
            for action in (separator, edit, more.menuAction()):
                action.setVisible(reviewing)

        qconnect(more.aboutToShow, fill_more)
        qconnect(menu.aboutToShow, update)
        update()

    gui_hooks.main_window_did_init.append(lambda: setup(aqt.mw))


def _patch_full_screen() -> None:
    from . import fullscreen

    fullscreen.apply()


def _patch_screen_edges() -> None:
    from . import screenedges

    screenedges.apply()


def _patch_splitters() -> None:
    """Add-ons such as AMBOSS put Anki's main view into a splitter beside a
    side panel, with desktop minimum widths (main view 400 px, the AMBOSS
    panel 624 px) that add up to more than a phone's screen; the splitter
    then lays the panel off the screen. Such splitters get a MainSplit."""
    import aqt
    from aqt.qt import QSplitter

    from .mainsplit import MainSplit

    def adopt(splitter: QSplitter, widget) -> None:  # type: ignore[no-untyped-def]
        mw = aqt.mw
        if mw is not None and widget is mw.web and not hasattr(splitter, "_kioku_split"):
            splitter._kioku_split = MainSplit(splitter)

    add, insert = QSplitter.addWidget, QSplitter.insertWidget

    def add_widget(self, widget):  # type: ignore[no-untyped-def]
        adopt(self, widget)
        add(self, widget)

    def insert_widget(self, index, widget):  # type: ignore[no-untyped-def]
        adopt(self, widget)
        insert(self, index, widget)

    QSplitter.addWidget = add_widget
    QSplitter.insertWidget = insert_widget


def _patch_docks() -> None:
    from . import maindocks

    maindocks.install()


def _patch_page_html() -> None:
    """Anki serves its pages (deck list, overview, reviewer, the bars) from
    its media server as /_anki/legacyPageData, without a viewport meta: put
    one in, so they are laid out for the phone from the first paint."""
    import aqt.mediasrv

    from . import webscripts

    set_page_html = aqt.mediasrv.MediaServer.set_page_html

    def with_viewport(self, id, html, *args, **kwargs):  # type: ignore[no-untyped-def]
        set_page_html(self, id, webscripts.with_viewport(html), *args, **kwargs)

    aqt.mediasrv.MediaServer.set_page_html = with_viewport


def _patch_update_check() -> None:
    """Anki's update prompts offer desktop Anki's download page (the check at
    startup) or its installer (Tools › Check for Updates), which don't work on
    a phone: Yes opens Kioku's releases instead, which bring the next Anki."""
    import aqt
    import aqt.update
    import aqt.utils

    aqt.appWebsiteDownloadSection = KIOKU_RELEASES
    aqt.update._download_github_update_and_install = lambda _release: aqt.utils.openLink(
        KIOKU_RELEASES
    )


def _patch_audio() -> None:
    import aqt.sound

    def setup_audio(taskman, base_folder: str, media_folder: str) -> None:
        aqt.sound.av_player.players.append(platform.audio_player(taskman, media_folder))
        aqt.sound.av_player.players.append(platform.tts_player(taskman))

    aqt.sound.setup_audio = setup_audio


def _python_313_compat() -> None:
    """Desktop Anki runs Python 3.13; the apps run 3.14, which dropped
    pkgutil.find_loader() and get_loader(). Add-ons' bundled libraries still
    call them (pytesseract in AnkiOCR)."""
    import importlib.util
    import pkgutil

    def find_loader(fullname):  # type: ignore[no-untyped-def]
        try:
            spec = importlib.util.find_spec(fullname)
        except (ImportError, ValueError):
            return None
        return spec.loader if spec else None

    def get_loader(module_or_name):  # type: ignore[no-untyped-def]
        if isinstance(module_or_name, types.ModuleType):
            spec = getattr(module_or_name, "__spec__", None)
            return spec.loader if spec else None
        return find_loader(module_or_name)

    if not hasattr(pkgutil, "find_loader"):
        pkgutil.find_loader = find_loader
    if not hasattr(pkgutil, "get_loader"):
        pkgutil.get_loader = get_loader


def _addon_platform() -> None:
    """platform.system() is "Android"/"iOS" since Python 3.13; add-ons pick
    programs and paths from tables keyed "Windows"/"Darwin"/"Linux" (and
    KeyError on anything else). Code in add-ons gets the answer older Pythons
    gave there: "Linux" on Android, "Darwin" on iOS; everything else (Anki's
    own platform description, truststore) the real one."""
    import platform
    import sys

    system = platform.system
    answer = {"android": "Linux", "ios": "Darwin"}.get(sys.platform)
    if not answer:
        return
    marker = f"{os.sep}addons21{os.sep}"

    def addon_system() -> str:
        caller = sys._getframe(1).f_globals.get("__file__") or ""
        return answer if marker in caller else system()

    platform.system = addon_system
