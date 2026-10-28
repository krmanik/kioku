"""Start Anki with defaults suited to a phone.

Anki reads its UI scale and video driver from the profile
metadata, overriding any environment variable, so patch the ProfileManager
accessors before Anki starts. The UI scale only changes the default; a value
set later in Preferences still wins (the remote screen has its own).
"""

import os
import subprocess
import sys


def provide_qtquick_stub() -> None:
    """Termux's pyqt6 is built without the QtQuick bindings. Anki imports them
    only to pick the Qt Quick graphics API, which QT_QUICK_BACKEND=software
    (set by session.sh) already does, so a stand-in is enough."""
    try:
        import PyQt6.QtQuick  # noqa: F401
        return
    except ImportError:
        pass
    import enum
    import types

    class QSGRendererInterface:
        class GraphicsApi(enum.Enum):
            Unknown = 0
            Software = 1
            OpenVG = 2
            OpenGL = 3
            Direct3D11 = 4
            Vulkan = 5
            Metal = 6
            Null = 7
            Direct3D12 = 8

    class QQuickWindow:
        @staticmethod
        def setGraphicsApi(api: "QSGRendererInterface.GraphicsApi") -> None:
            pass

    module = types.ModuleType("PyQt6.QtQuick")
    module.QQuickWindow = QQuickWindow
    module.QSGRendererInterface = QSGRendererInterface
    module.__all__ = ["QQuickWindow", "QSGRendererInterface"]
    sys.modules["PyQt6.QtQuick"] = module


def provide_opengl_placeholders() -> None:
    """Termux's pyqt6 is also built without Qt's OpenGL classes. Anki imports
    QOpenGLContext but only uses it on Qt 5, so a placeholder is enough."""
    from PyQt6 import QtGui

    for name in ("QOpenGLContext",):
        if not hasattr(QtGui, name):
            setattr(QtGui, name, type(name, (), {}))


def provide_accessible_names() -> None:
    """Termux's pyqt6 is also built without PyQt_Accessibility, which drops the
    accessible name and description accessors of QWidget and QTabBar. Add-ons
    call them (the Incremento add-on fails to load without them), and nothing
    reads them in the X11 session, so keep the values as Qt properties."""
    from PyQt6.QtWidgets import QTabBar, QWidget

    if hasattr(QWidget, "setAccessibleName"):
        return
    for name in ("accessibleName", "accessibleDescription"):
        setter = "set" + name[0].upper() + name[1:]
        setattr(QWidget, name, lambda self, key=name: self.property(key) or "")
        setattr(QWidget, setter, lambda self, value, key=name: self.setProperty(key, value))
    QTabBar.accessibleTabName = lambda self, index: self.property(f"accessibleTabName{index}") or ""
    QTabBar.setAccessibleTabName = lambda self, index, value: self.setProperty(f"accessibleTabName{index}", value)


provide_qtquick_stub()
provide_opengl_placeholders()
provide_accessible_names()

from aqt.profiles import ProfileManager, VideoDriver  # noqa: E402

DEFAULT_SCALE = float(os.environ.get("ANKIDX_SCALE", "2.0"))
# on the remote desktop's screen (ankidesk_remote.py): a computer's monitor
REMOTE = os.environ.get("ANKIDX_REMOTE") == "1"
# Preferences > Appearance > User interface size: one for the phone, one for
# the remote screen, which is a monitor
SCALE_KEY = "kioku_remote_uiScale" if REMOTE else "uiScale"
# in percent (Anki's own: 100 to 200)
SCALE_MIN, SCALE_MAX = 50, 300


def ui_scale(self: ProfileManager) -> float:
    scale = self.meta.get(SCALE_KEY, DEFAULT_SCALE)
    return min(max(scale, SCALE_MIN / 100), SCALE_MAX / 100)


def set_ui_scale(self: ProfileManager, scale: float) -> None:
    self.meta[SCALE_KEY] = scale


def video_driver(self: ProfileManager) -> VideoDriver:
    # No OpenGL stack is bundled.
    return VideoDriver.Software


def signal_ready() -> None:
    # Tells the Android app to swap its splash screen for the display.
    path = os.environ.get("ANKIDX_READY_FILE")
    if path:
        open(path, "w").close()


_setup_meta = ProfileManager.setupMeta


def setup_meta(self: ProfileManager):  # type: ignore[no-untyped-def]
    result = _setup_meta(self)
    # Anki 26.09 sets QT_SCALE_FACTOR only after creating the QApplication,
    # which Qt no longer reads then; set it as soon as the scale is known
    os.environ["QT_SCALE_FACTOR"] = str(self.uiScale())
    return result


ProfileManager.uiScale = ui_scale
ProfileManager.setUiScale = set_ui_scale
ProfileManager.video_driver = video_driver
ProfileManager.setupMeta = setup_meta

import aqt  # noqa: E402
import aqt.preferences  # noqa: E402
import aqt.update  # noqa: E402
import aqt.utils  # noqa: E402
from aqt import gui_hooks  # noqa: E402
from aqt.qt import QDesktopServices, QObject, QUrl, pyqtSlot  # noqa: E402

# Anki's update prompts offer desktop Anki's download page (the check at
# startup) or its installer (Tools > Check for Updates): Yes opens Kioku's
# releases instead, which bring the next Anki.
KIOKU_RELEASES = "https://github.com/krmanik/kioku/releases/latest"
aqt.appWebsiteDownloadSection = KIOKU_RELEASES
aqt.update._download_github_update_and_install = lambda _release: aqt.utils.openLink(KIOKU_RELEASES)


_setup_global = aqt.preferences.Preferences.setup_global
_update_global = aqt.preferences.Preferences.update_global


def setup_global(self) -> None:  # type: ignore[no-untyped-def]
    self.form.uiScale.setRange(SCALE_MIN, SCALE_MAX)
    _setup_global(self)


def update_global(self) -> None:  # type: ignore[no-untyped-def]
    _update_global(self)
    # Anki saves its global settings only when the profile closes; Android
    # stops the app without that when it's swiped away, which lost them
    self.mw.pm.save()


aqt.preferences.Preferences.setup_global = setup_global
aqt.preferences.Preferences.update_global = update_global


class UrlOpener(QObject):
    # Qt finds no launcher for web links without a desktop environment, so
    # openLink() did nothing; xdg-open (rootfs-overlay/bin) hands them to Android.
    @pyqtSlot(QUrl)
    def open(self, url: QUrl) -> None:
        subprocess.Popen(["xdg-open", url.toString()])


url_opener = UrlOpener()
for scheme in ("http", "https"):
    QDesktopServices.setUrlHandler(scheme, url_opener, "open")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ankidesk_mobile  # noqa: E402
# Preferences > Advanced, shared with the native apps (shared/python/kioku in
# the repository, with kioku_platform.py from here): the phone as a sync
# server, AnkiDroid's media folder
from kioku import advanced, ankidroid, syncserver  # noqa: E402

advanced.install()
ankidroid.install()
syncserver.install()

if REMOTE:
    # window sizes, splitters and table columns: the remote screen's own, so
    # each screen keeps what suits it
    _qt_state_key = aqt.utils._qt_state_key
    aqt.utils._qt_state_key = lambda kind, key: "kioku_remote_" + _qt_state_key(kind, key)

    def maximize_first_time() -> None:
        # after loadProfile() restored the window: with no size saved for the
        # remote screen yet, it has the phone's, tiny on a monitor
        key = aqt.utils._qt_state_key(aqt.utils._QtStateKeyKind.GEOMETRY, "mainWindow")
        if aqt.mw.pm.profile is not None and key not in aqt.mw.pm.profile:
            aqt.mw.showMaximized()

    gui_hooks.profile_did_open.append(maximize_first_time)
else:
    ankidesk_mobile.setup()
    # add-ons' side docks under the main view on the phone's narrow screen
    from kioku import maindocks

    maindocks.install()
gui_hooks.main_window_did_init.append(signal_ready)

aqt.run()
