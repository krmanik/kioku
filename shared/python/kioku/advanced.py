"""Preferences > Advanced: Kioku's own options for advanced users.

Everything here except gamepads is off by default and explains its risks
before it is turned on. The tab is added to Anki's Preferences dialog after it is built.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from kioku import ankidroid, gamepad, syncserver

logger = logging.getLogger("kioku.advanced")

LISTEN_LABELS = {
    syncserver.LOCAL: "This phone only",
    syncserver.TAILSCALE: "Tailscale",
    syncserver.ALL: "All networks (Wi-Fi, VPN)",
}

ENABLE_WARNING = """\
Kioku will run Anki's own sync server on this phone. AnkiDroid, Kioku's \
profiles and Anki on your computers can then sync with the phone instead of \
AnkiWeb.

• The server keeps its own copy of everything synced to it (collections and \
media) in Kioku's private storage, so it needs as much free space as your \
collection and media.
• It speaks plain HTTP. "This phone only" is safe; use "Tailscale" to reach \
it from your other devices; choose "All networks" only on a network you \
trust.
• A device that syncs here no longer syncs with AnkiWeb.
• The first time a device syncs, choose Upload on the device that has your \
cards, then Download on the others.
"""

PLATFORM_NOTE = {
    "android": "While the server runs, Android shows a notification and keeps "
    "Kioku running in the background.",
    "ios": "iOS pauses apps in the background: the server answers only while "
    "Kioku is open.",
}

HOW_TO_ANKIDROID = """\
<b>AnkiDroid:</b> Settings › Sync › Custom sync server: set <i>Sync url</i> \
to the address above, then log in with the user name and password.<br>"""

HOW_TO = """\
<b>Anki on a computer:</b> Preferences › Syncing › Self-hosted sync server: \
the address above; then log in.<br>\
<b>This Kioku profile:</b> “Use for this profile”."""


def install() -> None:
    import aqt.preferences

    original_init = aqt.preferences.Preferences.__init__

    def init(self, mw):  # type: ignore[no-untyped-def]
        original_init(self, mw)
        try:
            self.kioku_advanced = AdvancedTab(self)
            self.form.tabWidget.addTab(self.kioku_advanced.scroll, "Advanced")
        except Exception:
            logger.exception("adding the Advanced tab")

    aqt.preferences.Preferences.__init__ = init

    original_accept = aqt.preferences.Preferences.accept_with_callback

    def accept_with_callback(self, callback=None):  # type: ignore[no-untyped-def]
        tab = getattr(self, "kioku_advanced", None)
        after = tab.ankidroid.before_close() if tab and tab.ankidroid else None

        def done() -> None:
            if callback:
                callback()
            if after:
                after()
            else:
                from kioku import background

                # the sync server or this profile's sync settings may have changed
                background.refresh(self.mw)

        original_accept(self, done)

    aqt.preferences.Preferences.accept_with_callback = accept_with_callback

    from aqt import gui_hooks

    gui_hooks.main_window_did_init.append(lambda: apply_background(aqt.mw))


# --- Background (iOS): keep add-on servers answering ---------------------------

BACKGROUND_KEY = "kioku_keep_running_in_background"

BACKGROUND_NOTE = """\
iOS pauses Kioku a few seconds after you leave it, so add-ons that answer \
other apps, such as AnkiConnect, stop answering. With this on, Kioku asks \
for location updates and keeps running like a navigation app. Kioku \
ignores the location: it isn’t saved or sent. It uses some battery; iOS \
shows the location arrow when Kioku goes to the background."""

BACKGROUND_WARNING = """\
Kioku will ask iOS for location access, to keep running in the background.

• Kioku ignores the location: it isn’t saved, shown or sent anywhere.
• Add-ons are programs that run inside Kioku. Kioku lets only itself use \
location, but an add-on written to get around that could read it while \
access is allowed. Keep Precise Location off (iOS’s default for Kioku) and \
install only add-ons you trust.
• Location stays allowed until you change it in the Settings app › Apps › \
Kioku › Location; turning this option off stops Kioku using it."""

BACKGROUND_STATUS = {
    "off": "",
    "allowed": "Off. iOS still allows Kioku location access; to take it back: "
    "Settings app › Apps › Kioku › Location › Never.",
    "asking": "Waiting for location access.",
    "denied": "Location access is off for Kioku: turn it on in the Settings app › "
    "Apps › Kioku › Location (While Using the App).",
    "on": "On: Kioku keeps running in the background.",
}


def background_wanted(meta: dict | None) -> bool:
    return bool((meta or {}).get(BACKGROUND_KEY))


def apply_background(mw) -> None:  # type: ignore[no-untyped-def]
    import kioku_platform as platform

    keep = getattr(platform, "keep_running_in_background", None)
    if keep is not None and mw is not None:
        try:
            keep(background_wanted(mw.pm.meta))
        except Exception:
            logger.exception("keep running in the background")


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "bytes" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} bytes"


class AdvancedTab:
    def __init__(self, prefs: Any) -> None:
        from aqt.qt import QScrollArea, QVBoxLayout, QWidget

        self.prefs = prefs
        self.mw = prefs.mw
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        self.layout = QVBoxLayout(body)
        self.scroll.setWidget(body)
        self.server = SyncServerGroup(self)
        self.layout.addWidget(self.server.box)
        import kioku_platform as platform

        # only where the platform reads controllers (iOS, Android); the Termux
        # app's X11 desktop gets no gamepad events
        self.gamepad: GamepadGroup | None = None
        if hasattr(platform, "watch_gamepads"):
            self.gamepad = GamepadGroup(self)
            self.layout.addWidget(self.gamepad.box)
        self.background: BackgroundGroup | None = None
        if hasattr(platform, "keep_running_in_background"):
            self.background = BackgroundGroup(self)
            self.layout.addWidget(self.background.box)
        self.ankidroid: AnkiDroidGroup | None = None
        if sys.platform == "android" and self.mw.col is not None:
            self.ankidroid = AnkiDroidGroup(self)
            self.layout.addWidget(self.ankidroid.box)
        self.layout.addStretch(1)


class GamepadGroup:
    """Gamepads and game controllers (kioku.gamepad): on or off, and the
    buttons of each action."""

    def __init__(self, tab: AdvancedTab) -> None:
        from aqt.qt import QCheckBox, QGroupBox, QLabel, QPushButton, QVBoxLayout, qconnect

        self.mw = tab.mw
        self.box = QGroupBox("Gamepad")
        layout = QVBoxLayout(self.box)
        self.enabled = QCheckBox("Use gamepads and game controllers")
        self.enabled.setChecked(gamepad.load_settings(self.mw.pm.meta).enabled)
        qconnect(self.enabled.toggled, self._on_enabled)
        layout.addWidget(self.enabled)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QPushButton("Controls…")
        qconnect(self.buttons.clicked, self._on_buttons)
        layout.addWidget(self.buttons)
        self._refresh()

    def _refresh(self) -> None:
        pads = gamepad.instance()
        names = sorted(pads.controllers.values()) if pads else []
        self.status.setText(
            "Connected: " + ", ".join(names)
            if names
            else "None connected. Pair a Bluetooth controller in the system settings, or plug one in."
        )
        self.buttons.setEnabled(self.enabled.isChecked())

    def _on_enabled(self, on: bool) -> None:
        settings = gamepad.load_settings(self.mw.pm.meta)
        settings.enabled = on
        gamepad.save_settings(self.mw.pm, settings)
        gamepad.settings_changed()
        self._refresh()

    def _on_buttons(self) -> None:
        gamepad.ControlsDialog(self.box.window(), self.mw.pm).exec()


class BackgroundGroup:
    """iOS: keep Kioku running in the background (location updates) so
    add-on servers keep answering."""

    def __init__(self, tab: AdvancedTab) -> None:
        from aqt.qt import QCheckBox, QGroupBox, QLabel, QTimer, QVBoxLayout, qconnect

        self.mw = tab.mw
        self.box = QGroupBox("Background")
        layout = QVBoxLayout(self.box)
        self.enabled = QCheckBox("Keep running in the background")
        self.enabled.setChecked(background_wanted(self.mw.pm.meta))
        qconnect(self.enabled.toggled, self._on_enabled)
        layout.addWidget(self.enabled)
        note = QLabel(BACKGROUND_NOTE)
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        # location access is answered in a system alert
        self.timer = QTimer(self.box)
        qconnect(self.timer.timeout, self._refresh)
        self.timer.start(1000)
        self._refresh()

    def _refresh(self) -> None:
        import kioku_platform as platform

        get = getattr(platform, "keep_running_in_background_status", None)
        state = get() if get else ("on" if self.enabled.isChecked() else "off")
        self.status.setText(BACKGROUND_STATUS.get(state, ""))
        self.status.setVisible(bool(self.status.text()))

    def _on_enabled(self, on: bool) -> None:
        from aqt.utils import askUser

        if on and not askUser(BACKGROUND_WARNING, parent=self.box.window(), title="Background"):
            from aqt.qt import QSignalBlocker

            blocker = QSignalBlocker(self.enabled)
            self.enabled.setChecked(False)
            del blocker
            return
        self.mw.pm.meta[BACKGROUND_KEY] = on
        pm = self.mw.pm
        # like gamepad.save_settings: the profile list has no pm.save()
        pm.db.execute("update profiles set data = ? where name = ?", pm._pickle(pm.meta), "_global")
        pm.db.commit()
        apply_background(self.mw)
        self._refresh()


class SyncServerGroup:
    def __init__(self, tab: AdvancedTab) -> None:
        import sys

        from aqt.qt import (
            QCheckBox,
            QComboBox,
            QFormLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QSpinBox,
            QVBoxLayout,
            QWidget,
            qconnect,
        )

        self.tab = tab
        self.mw = tab.mw
        self.settings = syncserver.load_settings(self.mw.pm.meta)
        if not self.settings.password:
            # saved with the first change; until then the fields stay valid
            self.settings.password = syncserver.new_password()
        self._busy = False

        self.box = QGroupBox("Sync server on this phone")
        layout = QVBoxLayout(self.box)

        self.enabled = QCheckBox("Run a sync server on this phone")
        layout.addWidget(self.enabled)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.listen = QComboBox()
        for key in syncserver.LISTEN_CHOICES:
            self.listen.addItem(LISTEN_LABELS[key], key)
        form.addRow("Listen on", self.listen)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        form.addRow("Port", self.port)
        self.username = QLineEdit()
        form.addRow("User name", self.username)
        password_row = QWidget()
        row = QHBoxLayout(password_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.password = QLineEdit()
        row.addWidget(self.password, 1)
        self.new_password = QPushButton("New")
        row.addWidget(self.new_password)
        form.addRow("Password", password_row)
        layout.addLayout(form)

        self.addresses = QLabel()
        self.addresses.setWordWrap(True)
        self.addresses.setTextInteractionFlags(
            self.addresses.textInteractionFlags()
            | self.addresses.textInteractionFlags().TextSelectableByMouse
        )
        layout.addWidget(self.addresses)
        buttons = QHBoxLayout()
        self.copy = QPushButton("Copy address")
        self.use_here = QPushButton("Use for this profile")
        buttons.addWidget(self.copy)
        buttons.addWidget(self.use_here)
        layout.addLayout(buttons)

        how = QLabel((HOW_TO_ANKIDROID if sys.platform == "android" else "") + HOW_TO)
        how.setWordWrap(True)
        layout.addWidget(how)
        import kioku_platform as platform

        if note := getattr(platform, "SERVER_NOTE", PLATFORM_NOTE.get(sys.platform)):
            note_label = QLabel(note)
            note_label.setWordWrap(True)
            layout.addWidget(note_label)

        data_row = QHBoxLayout()
        self.storage = QLabel()
        self.storage.setWordWrap(True)
        data_row.addWidget(self.storage, 1)
        self.delete = QPushButton("Delete server data…")
        data_row.addWidget(self.delete)
        layout.addLayout(data_row)

        self._fill()
        qconnect(self.enabled.toggled, self._on_enabled)
        qconnect(self.listen.currentIndexChanged, lambda _i: self._on_changed())
        qconnect(self.port.editingFinished, self._on_changed)
        qconnect(self.username.editingFinished, self._on_changed)
        qconnect(self.password.editingFinished, self._on_changed)
        qconnect(self.new_password.clicked, self._on_new_password)
        qconnect(self.copy.clicked, self._on_copy)
        qconnect(self.use_here.clicked, self._on_use_here)
        qconnect(self.delete.clicked, self._on_delete)
        self._refresh()

    # Showing
    ##################################################################

    def _fill(self) -> None:
        from aqt.qt import QSignalBlocker

        s = self.settings
        blockers = [QSignalBlocker(w) for w in (self.enabled, self.listen)]
        self.enabled.setChecked(s.enabled)
        self.listen.setCurrentIndex(max(0, self.listen.findData(s.listen)))
        self.port.setValue(s.port)
        self.username.setText(s.username)
        self.password.setText(s.password)
        del blockers

    def _refresh(self) -> None:
        st = syncserver.status()
        s = self.settings
        if self._busy:
            text, color = "Working…", None
        elif st.running:
            text, color = f"Running on port {st.port}.", None
        elif st.error:
            text, color = st.error, "red"
        elif s.enabled:
            # stopped from Android's notification
            text, color = "Stopped. It starts again with Kioku, or turn it off and on here.", None
        else:
            text, color = "Off.", None
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};" if color else "")

        found = syncserver.urls(s, st.host if st.running else None)
        if found:
            self.addresses.setText(
                "<br>".join(f"{who}:<br><b>{url}</b>" for who, url in found)
            )
        else:
            self.addresses.setText("Tailscale isn't connected.")
        self.copy.setEnabled(bool(found))
        self.use_here.setEnabled(st.running and self.mw.col is not None)
        for w in (self.listen, self.port, self.username, self.password, self.new_password):
            w.setEnabled(not self._busy)
        self.enabled.setEnabled(not self._busy)
        self._update_storage()

    def _update_storage(self) -> None:
        def done(fut):  # type: ignore[no-untyped-def]
            try:
                size = fut.result()
            except Exception:
                size = 0
            try:
                self.storage.setText(f"Server data: {_human_size(size)}")
                self.delete.setEnabled(size > 0 and not self._busy)
            except RuntimeError:
                pass  # the dialog closed

        self.mw.taskman.run_in_background(
            syncserver.storage_used, done, uses_collection=False
        )

    # Running
    ##################################################################

    def _run(self, work, after=None) -> None:  # type: ignore[no-untyped-def]
        """Starts/stops the server off the main thread."""
        self._busy = True
        self._refresh()

        def done(fut):  # type: ignore[no-untyped-def]
            self._busy = False
            try:
                fut.result()
            except Exception:
                logger.exception("sync server")
            try:
                self._refresh()
                if after:
                    after()
            except RuntimeError:
                pass

        self.mw.taskman.run_in_background(work, done, uses_collection=False)

    def _save(self) -> None:
        syncserver.save_settings(self.mw.pm, self.settings)

    def _on_enabled(self, on: bool) -> None:
        from aqt.utils import askUser

        if on:
            if not askUser(ENABLE_WARNING, parent=self.tab.prefs, title="Sync server"):
                from aqt.qt import QSignalBlocker

                blocker = QSignalBlocker(self.enabled)
                self.enabled.setChecked(False)
                del blocker
                return
        self.settings.enabled = on
        self._save()
        settings = syncserver.Settings(**vars(self.settings))
        if on:
            self._run(lambda: syncserver.start(settings))
        else:
            self._run(syncserver.stop)

    def _read_fields(self) -> syncserver.Settings:
        return syncserver.Settings(
            enabled=self.settings.enabled,
            listen=self.listen.currentData(),
            port=self.port.value(),
            username=self.username.text().strip(),
            password=self.password.text(),
        )

    def _on_changed(self) -> None:
        new = self._read_fields()
        if new == self.settings:
            return
        if problem := new.problem():
            from aqt.utils import showWarning

            showWarning(problem, parent=self.tab.prefs)
            self._fill()
            return
        moved = (new.port, new.username, new.password) != (
            self.settings.port,
            self.settings.username,
            self.settings.password,
        )
        self.settings = new
        self._save()
        if new.enabled:
            settings = syncserver.Settings(**vars(new))
            self._run(lambda: syncserver.start(settings))
        else:
            self._refresh()
        if moved and new.enabled:
            from aqt.utils import tooltip

            tooltip(
                "Devices that sync here need the new address or login.",
                parent=self.tab.prefs,
            )

    def _on_new_password(self) -> None:
        self.password.setText(syncserver.new_password())
        self._on_changed()

    def _on_copy(self) -> None:
        from aqt.qt import QApplication
        from aqt.utils import tooltip

        st = syncserver.status()
        found = syncserver.urls(self.settings, st.host if st.running else None)
        if found:
            QApplication.clipboard().setText(found[0][1])
            tooltip("Copied.", parent=self.tab.prefs)

    # This profile
    ##################################################################

    def own_url(self) -> str | None:
        return syncserver.own_url()

    def _on_use_here(self) -> None:
        from aqt.utils import askUser, showWarning, tooltip

        mw = self.mw
        url = self.own_url()
        if url is None or mw.col is None:
            return
        pm = mw.pm
        current = pm.custom_sync_url()
        logged_in = bool(pm.profile.get("syncKey"))
        if logged_in and current != url:
            where = current or "AnkiWeb"
            if not askUser(
                f"This profile syncs with {where}. Switch it to this phone's sync "
                "server? It will be logged out there.\n\nIf the server is empty, "
                "choose Upload at the next sync.",
                parent=self.tab.prefs,
            ):
                return
        settings = self.settings

        def login():  # type: ignore[no-untyped-def]
            return mw.col.sync_login(
                username=settings.username, password=settings.password, endpoint=url
            )

        def done(fut):  # type: ignore[no-untyped-def]
            try:
                auth = fut.result()
            except Exception as err:
                showWarning(f"Logging in to the sync server failed:\n{err}", parent=self.tab.prefs)
                return
            pm.clear_sync_auth()
            pm.set_custom_sync_url(url)
            pm.set_sync_key(auth.hkey)
            pm.set_sync_username(settings.username)
            prefs = self.tab.prefs
            try:
                # Preferences writes its fields back when it closes
                prefs.form.custom_sync_url.setText(url)
                prefs.update_login_status()
            except RuntimeError:
                pass
            tooltip("This profile now syncs with the phone's server.", parent=prefs)

        mw.taskman.with_progress(login, done, parent=self.tab.prefs)

    def _on_delete(self) -> None:
        from aqt.utils import askUser

        if not askUser(
            "Delete everything synced to this phone's server (all collections and "
            "media)? Devices keep their own copies; the next sync of each needs a "
            "full upload.\n\nThis can't be undone.",
            parent=self.tab.prefs,
            defaultno=True,
        ):
            return
        settings = syncserver.Settings(**vars(self.settings))

        def work() -> None:
            was_running = syncserver.status().running
            syncserver.stop()
            syncserver.delete_data()
            if was_running and settings.enabled:
                syncserver.start(settings)

        self._run(work)


# (button, explanation below it): a radio button's text doesn't wrap
MODE_LABELS = {
    ankidroid.OFF: ("Kioku's own collection", ""),
    ankidroid.MEDIA: (
        "AnkiDroid's media",
        "Use AnkiDroid's media folder; sync the cards with AnkiDroid through "
        "the sync server above. Both apps can stay open.",
    ),
    ankidroid.FOLDER: (
        "AnkiDroid's collection",
        "Open AnkiDroid's own collection. Only one of the two apps can have it "
        "open at a time.",
    ),
}
FOLDER_UNAVAILABLE_LABEL = (
    "AnkiDroid's collection (not available)",
    "Opening AnkiDroid's own collection could lose changes: tap for why.",
)

FOLDER_UNAVAILABLE = """Opening AnkiDroid's own collection isn't available, \
because it can lose your changes.

Why: Anki locks a collection while it is open, so that only one app can change \
it. But Anki's automatic backups (in Kioku and in AnkiDroid) release that lock \
while the collection stays open. After one, Kioku and AnkiDroid could both \
have the collection open and change it at once, and one app's changes get \
lost. This happened while testing, and no app can tell from the outside that \
the lock is gone.

Instead, choose “AnkiDroid's media” and sync the two apps through the sync \
server on this phone; media still exists only once:

• Kioku: turn the sync server on and tap “Use for this profile”. Keep \
“Automatically sync on profile open/close” on (Preferences › Syncing): Kioku \
then syncs when you leave it and when you come back.
• AnkiDroid: Settings › Sync: set the custom sync server, log in, turn on \
Automatic synchronization, and turn off Fetch media on sync (else AnkiDroid \
uploads its media to the server, a second copy). AnkiDroid syncs by itself \
only when it starts or closes and its last sync was over 10 minutes ago: \
tap its Sync button after switching to see Kioku's latest changes, and \
before switching back.

A change reaches the other app once both have synced. If both apps change the \
same card in between, the later change wins, as with any Anki sync."""

ANKIDROID_INTRO = """For AnkiDroid builds that keep their folder in shared storage, such as the \
GitHub "full" build (usually /storage/emulated/0/AnkiDroid). The Play Store \
build keeps it where no other app can read it: use the sync server instead."""

MODE_WARNING = {
    ankidroid.MEDIA: """This profile will use AnkiDroid's collection.media folder instead of its own \
media, so large media exists only once on the phone. Its cards still come \
from its own collection, which you sync with AnkiDroid through the sync \
server on this phone.

• Media sync is turned off for this profile; turn off "Fetch media on sync" \
in AnkiDroid too, or AnkiDroid uploads all its media to the server.
• Media this profile adds goes straight into AnkiDroid's folder.
• Check Media won't delete unused files unless you allow it below: a file \
may belong to a card AnkiDroid hasn't synced yet.
• This profile's own media folder is left as it is.

Cards reach AnkiDroid only through syncing. With “Automatically sync on \
profile open/close” on (Preferences › Syncing), Kioku syncs when you leave it \
and when you come back. AnkiDroid syncs by itself only on start or exit and \
at most every 10 minutes: tap its Sync button after switching.""",
    ankidroid.FOLDER: """This profile will open AnkiDroid's own collection. Anki locks a collection \
while it is open, so only one app can have it:

• Close AnkiDroid completely (Force stop) before opening it in Kioku.
• Kioku closes the collection whenever it goes to the background, and opens \
it again when you come back. If AnkiDroid opened it meanwhile, Kioku waits \
until AnkiDroid is closed.
• Keep AnkiDroid up to date: both apps change the same file.
• Media sync is turned off for this profile; AnkiDroid keeps syncing media.
• This profile's own collection is kept and comes back if you switch back.""",
}


class AnkiDroidGroup:
    def __init__(self, tab: AdvancedTab) -> None:
        from aqt.qt import (
            QButtonGroup,
            QCheckBox,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QRadioButton,
            QVBoxLayout,
            qconnect,
        )

        self.tab = tab
        self.mw = tab.mw
        self.saved = ankidroid.current(self.mw)

        self.box = QGroupBox("AnkiDroid's folder (this profile)")
        layout = QVBoxLayout(self.box)
        intro = QLabel(ANKIDROID_INTRO)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.modes = QButtonGroup(self.box)
        self.radios = {}
        for index, mode in enumerate(ankidroid.MODES):
            title, explanation = MODE_LABELS[mode]
            if mode == ankidroid.FOLDER and not ankidroid.FOLDER_READY:
                title, explanation = FOLDER_UNAVAILABLE_LABEL
            radio = QRadioButton(title)
            self.radios[mode] = radio
            self.modes.addButton(radio, index)
            layout.addWidget(radio)
            if explanation:
                label = QLabel(explanation)
                label.setWordWrap(True)
                label.setContentsMargins(24, 0, 0, 0)
                layout.addWidget(label)

        row = QHBoxLayout()
        self.folder = QLineEdit()
        row.addWidget(self.folder, 1)
        self.find = QPushButton("Find")
        row.addWidget(self.find)
        layout.addWidget(QLabel("AnkiDroid folder"))
        layout.addLayout(row)

        self.checks = QLabel()
        self.checks.setWordWrap(True)
        layout.addWidget(self.checks)
        buttons = QHBoxLayout()
        self.grant = QPushButton("Allow All files access…")
        self.app_info = QPushButton("AnkiDroid app info…")
        buttons.addWidget(self.grant)
        buttons.addWidget(self.app_info)
        layout.addLayout(buttons)

        self.allow_delete = QCheckBox("Allow Check Media to delete unused files")
        layout.addWidget(self.allow_delete)
        note = QLabel("Changes take effect when you close Preferences: the profile opens again.")
        note.setWordWrap(True)
        layout.addWidget(note)

        if self.saved.mode == ankidroid.FOLDER and not ankidroid.FOLDER_READY:
            # opening the profile fell back already; never offer it back
            self.saved.mode = ankidroid.OFF
        self.radios[self.saved.mode].setChecked(True)
        self.folder.setText(self.saved.folder)
        self.allow_delete.setChecked(self.saved.allow_delete_unused)
        self._mode = self.saved.mode

        qconnect(self.modes.idClicked, self._on_mode)
        qconnect(self.folder.editingFinished, self.refresh)
        qconnect(self.find.clicked, self._on_find)
        qconnect(self.grant.clicked, self._on_grant)
        qconnect(self.app_info.clicked, self._on_app_info)
        self._watch_app_state()
        self.refresh()

    def chosen(self) -> ankidroid.Source:
        return ankidroid.Source(
            mode=self._mode,
            folder=self.folder.text().strip().rstrip("/") or ankidroid.DEFAULT_FOLDER,
            allow_delete_unused=self.allow_delete.isChecked(),
        )

    # Showing
    ##################################################################

    def refresh(self) -> None:
        import kioku_platform as platform

        source = self.chosen()
        lines = []
        try:
            access = platform.all_files_access()
        except Exception:
            access = False
        lines.append(("✓" if access else "✗") + " All files access")
        installed: dict[str, str] = {}
        try:
            installed = platform.app_versions(list(ankidroid.PACKAGES))
        except Exception:
            logger.exception("AnkiDroid versions")
        if installed:
            for package, version in installed.items():
                old = ankidroid.version_too_old(version)
                lines.append(
                    ("⚠ " if old else "✓ ")
                    + f"AnkiDroid {version} ({package})"
                    + (" is older than Kioku's Anki; update it first." if old else "")
                )
        else:
            lines.append("✗ AnkiDroid isn't installed")
        if access:
            have_col = os.path.isfile(source.collection)
            have_media = os.path.isdir(source.media)
            lines.append(("✓" if have_media else "✗") + " collection.media")
            lines.append(("✓" if have_col else "✗") + " collection.anki2")
        if source.mode == ankidroid.MEDIA:
            st = syncserver.status()
            url = self.tab.server.own_url()
            uses = url is not None and self.mw.pm.custom_sync_url() == url
            if not st.running:
                lines.append("✗ The sync server above isn't running")
            elif not uses:
                lines.append("✗ This profile doesn't sync with the server yet: “Use for this profile”")
            else:
                lines.append("✓ This profile syncs with the phone's server")
            if not self.mw.pm.auto_syncing_enabled():
                lines.append(
                    "✗ Automatic sync is off (Preferences › Syncing): changes reach "
                    "AnkiDroid only when you sync by hand"
                )
        self.checks.setText("<br>".join(_escape(line) for line in lines))
        self.grant.setVisible(not access)
        self.app_info.setVisible(bool(installed))
        self.allow_delete.setEnabled(source.mode != ankidroid.OFF)
        for w in (self.folder, self.find):
            w.setEnabled(source.mode != ankidroid.OFF)

    def _watch_app_state(self) -> None:
        from aqt.qt import QGuiApplication, Qt

        def on_state(state):  # type: ignore[no-untyped-def]
            if state == Qt.ApplicationState.ApplicationActive:
                try:
                    self.refresh()
                except RuntimeError:
                    pass  # the dialog closed

        app = QGuiApplication.instance()
        app.applicationStateChanged.connect(on_state)
        self.box.destroyed.connect(lambda *_: _disconnect(app.applicationStateChanged, on_state))

    # Actions
    ##################################################################

    def _on_mode(self, index: int) -> None:
        from aqt.utils import askUser

        mode = ankidroid.MODES[index]
        if mode == ankidroid.FOLDER and not ankidroid.FOLDER_READY:
            from aqt.utils import showText

            self.radios[self._mode].setChecked(True)
            # scrollable: a message box taller than the screen gets squashed
            showText(FOLDER_UNAVAILABLE, parent=self.tab.prefs, title="AnkiDroid's collection")
            return
        if mode != ankidroid.OFF and mode != self.saved.mode:
            if not askUser(MODE_WARNING[mode], parent=self.tab.prefs, title="AnkiDroid's folder"):
                self.radios[self._mode].setChecked(True)
                return
        self._mode = mode
        self.refresh()

    def _on_find(self) -> None:
        from aqt.utils import showInfo, tooltip

        found = ankidroid.find_folders()
        if not found:
            showInfo(
                "No folder with an Anki collection was found in shared storage. "
                "Is All files access allowed, and does AnkiDroid keep its folder there?",
                parent=self.tab.prefs,
            )
            return
        self.folder.setText(found[0])
        if len(found) > 1:
            tooltip("Also found: " + ", ".join(found[1:]), parent=self.tab.prefs)
        self.refresh()

    def _on_grant(self) -> None:
        import kioku_platform as platform

        platform.request_all_files_access()

    def _on_app_info(self) -> None:
        import kioku_platform as platform

        installed = platform.app_versions(list(ankidroid.PACKAGES))
        if installed:
            platform.open_app_details(next(iter(installed)))

    # Applying
    ##################################################################

    def before_close(self):  # type: ignore[no-untyped-def]
        """Saves the choice into the profile before Preferences writes it;
        returns what to run once Preferences closed, or None."""
        from aqt.utils import showWarning

        new = self.chosen()
        if new == self.saved:
            return None
        if problems := ankidroid.problems(new):
            showWarning(
                "AnkiDroid's folder can't be used, so this profile keeps its "
                "current setting:\n\n" + "\n".join(problems),
                parent=self.tab.prefs,
            )
            if new.mode == self.saved.mode:
                return None
            new.mode = self.saved.mode
        reopen = (new.mode, new.folder) != (self.saved.mode, self.saved.folder) and (
            new.mode != ankidroid.OFF or self.saved.mode != ankidroid.OFF
        )
        ankidroid.store(self.mw.pm.profile, new)
        if new.mode != ankidroid.OFF and new.mode != self.saved.mode:
            # Preferences writes this checkbox into the profile when it closes
            self.tab.prefs.form.syncMedia.setChecked(False)
        if not reopen:
            return None
        mw = self.mw

        def reopen_profile() -> None:
            mw.unloadProfile(lambda: mw.loadProfile())

        return lambda: mw.progress.single_shot(100, reopen_profile, False)


def _escape(text: str) -> str:
    import html

    return html.escape(text, quote=False)


def _disconnect(signal, slot) -> None:  # type: ignore[no-untyped-def]
    try:
        signal.disconnect(slot)
    except (TypeError, RuntimeError):
        pass
