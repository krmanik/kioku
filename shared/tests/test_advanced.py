"""Preferences > Advanced (kioku.advanced) with an offscreen Qt and a stand-in
for Anki's main window."""

from __future__ import annotations

import os
from concurrent.futures import Future

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from anki.collection import Collection
from aqt.qt import QApplication, QCheckBox, QLineEdit, QTabWidget, QWidget

from kioku import advanced, ankidroid, syncserver
from test_syncserver import free_port, new_col

app = QApplication.instance() or QApplication([])


class TaskMan:
    """Runs background work at once, like a finished QueryOp."""

    def run_in_background(self, task, on_done=None, args=None, uses_collection=True):  # type: ignore[no-untyped-def]
        fut: Future = Future()
        try:
            fut.set_result(task(**(args or {})))
        except Exception as err:
            fut.set_exception(err)
        if on_done:
            on_done(fut)
        return fut

    def with_progress(self, task, on_done=None, parent=None, **kw):  # type: ignore[no-untyped-def]
        return self.run_in_background(task, on_done)


class PM:
    def __init__(self, db) -> None:  # type: ignore[no-untyped-def]
        from aqt.profiles import ProfileManager

        self.db = db
        self.meta: dict = {}
        self.profile: dict = {}
        self._pickle = lambda obj: ProfileManager._pickle(self, obj)
        db.execute("insert into profiles values ('_global', ?)", self._pickle(self.meta))

    def custom_sync_url(self):  # type: ignore[no-untyped-def]
        return self.profile.get("customSyncUrl")

    def set_custom_sync_url(self, url) -> None:  # type: ignore[no-untyped-def]
        self.profile["customSyncUrl"] = url

    def set_sync_key(self, key) -> None:  # type: ignore[no-untyped-def]
        self.profile["syncKey"] = key

    def set_sync_username(self, name) -> None:  # type: ignore[no-untyped-def]
        self.profile["syncUser"] = name

    def auto_syncing_enabled(self) -> bool:
        return self.profile.get("autoSync", True)

    def clear_sync_auth(self) -> None:
        for key in ("syncKey", "syncUser", "currentSyncUrl"):
            self.profile.pop(key, None)


class Prefs(QWidget):
    def __init__(self, mw) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.mw = mw
        self.form = type("Form", (), {})()
        self.form.tabWidget = QTabWidget(self)
        self.form.custom_sync_url = QLineEdit(self)
        self.form.syncMedia = QCheckBox(self)
        self.form.syncMedia.setChecked(True)
        self.login_status_updates = 0

    def update_login_status(self) -> None:
        self.login_status_updates += 1


@pytest.fixture
def prefs(platform, tmp_path, monkeypatch):
    from anki.db import DB

    db = DB(str(tmp_path / "prefs21.db"))
    db.execute("create table profiles (name text primary key, data blob not null)")
    mw = type("MW", (), {})()
    mw.pm = PM(db)
    mw.taskman = TaskMan()
    mw.col = new_col(tmp_path / "profile" / "collection.anki2")
    answers: list[bool] = []
    monkeypatch.setattr("aqt.utils.askUser", lambda *a, **k: answers.pop(0) if answers else True)
    monkeypatch.setattr("aqt.utils.showWarning", lambda text, **k: warnings.append(text))
    monkeypatch.setattr("aqt.utils.tooltip", lambda *a, **k: None)
    warnings: list[str] = []
    p = Prefs(mw)
    p.answers = answers
    p.warnings = warnings
    yield p
    mw.col.close()


def make_tab(prefs) -> advanced.SyncServerGroup:  # type: ignore[no-untyped-def]
    tab = advanced.AdvancedTab(prefs)
    prefs.form.tabWidget.addTab(tab.scroll, "Advanced")
    return tab.server


def test_off_by_default(prefs) -> None:
    group = make_tab(prefs)
    assert not group.enabled.isChecked()
    assert group.status.text() == "Off."
    assert not group.use_here.isEnabled()
    assert not syncserver.status().running


def test_declining_the_warning_keeps_it_off(prefs) -> None:
    group = make_tab(prefs)
    prefs.answers.append(False)
    group.enabled.setChecked(True)
    assert not group.enabled.isChecked()
    assert not syncserver.status().running
    assert not syncserver.load_settings(prefs.mw.pm.meta).enabled


def test_enable_starts_with_a_new_password(prefs) -> None:
    group = make_tab(prefs)
    group.port.setValue(free_port())
    group.port.editingFinished.emit()
    group.enabled.setChecked(True)
    st = syncserver.status()
    assert st.running, st
    saved = syncserver.load_settings(prefs.mw.pm.meta)
    assert saved.enabled and len(saved.password) >= 8
    assert group.password.text() == saved.password
    assert "Running" in group.status.text()
    assert f"127.0.0.1:{st.port}" in group.addresses.text()
    assert group.use_here.isEnabled()
    # settings survive a new Preferences window (read back from the db)
    from aqt.profiles import ProfileManager

    data = prefs.mw.pm.db.scalar("select cast(data as blob) from profiles where name = '_global'")
    assert syncserver.load_settings(ProfileManager._unpickle(None, data)) == saved

    group.enabled.setChecked(False)
    assert not syncserver.status().running
    assert group.status.text() == "Off."


def test_stopped_from_the_notification(prefs) -> None:
    group = make_tab(prefs)
    group.port.setValue(free_port())
    group.port.editingFinished.emit()
    group.enabled.setChecked(True)
    syncserver.stop()  # what the notification's Stop does
    group._refresh()
    assert group.enabled.isChecked()
    assert group.status.text().startswith("Stopped.")
    # turning it off and on starts it again
    group.enabled.setChecked(False)
    group.enabled.setChecked(True)
    assert syncserver.status().running


def test_changing_the_port_restarts(prefs) -> None:
    group = make_tab(prefs)
    group.port.setValue(free_port())
    group.port.editingFinished.emit()
    group.enabled.setChecked(True)
    new_port = free_port()
    group.port.setValue(new_port)
    group.port.editingFinished.emit()
    assert syncserver.status().port == new_port
    assert syncserver.answers()


def test_settings_before_first_enable(prefs) -> None:
    group = make_tab(prefs)
    port = free_port()
    group.port.setValue(port)
    group.port.editingFinished.emit()
    assert not prefs.warnings
    saved = syncserver.load_settings(prefs.mw.pm.meta)
    assert saved.port == port and not saved.enabled
    assert saved.password == group.password.text() and len(saved.password) >= 8


def test_bad_values_are_refused(prefs) -> None:
    group = make_tab(prefs)
    group.username.setText("a:b")
    group.username.editingFinished.emit()
    assert prefs.warnings and "user name" in prefs.warnings[-1]
    assert group.username.text() == "kioku"
    group.password.setText("short")
    group.password.editingFinished.emit()
    assert "8 characters" in prefs.warnings[-1]


def test_port_in_use_shows_the_error(prefs) -> None:
    import socket

    group = make_tab(prefs)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        group.port.setValue(busy.getsockname()[1])
        group.port.editingFinished.emit()
        group.enabled.setChecked(True)
        assert "already in use" in group.status.text()
        assert "red" in group.status.styleSheet()
        assert not group.use_here.isEnabled()


def test_use_for_this_profile(prefs) -> None:
    group = make_tab(prefs)
    group.port.setValue(free_port())
    group.port.editingFinished.emit()
    group.enabled.setChecked(True)
    pm = prefs.mw.pm
    pm.profile.update(syncKey="ankiweb-key", syncUser="me@example.com")
    prefs.answers.append(False)  # don't leave AnkiWeb
    group.use_here.click()
    assert pm.profile["syncKey"] == "ankiweb-key"

    group.use_here.click()  # and now yes
    url = f"http://127.0.0.1:{syncserver.status().port}/"
    assert pm.custom_sync_url() == url
    assert pm.profile["syncUser"] == "kioku"
    assert pm.profile["syncKey"] != "ankiweb-key"
    # Preferences writes its own field back on close: it must hold the URL
    assert prefs.form.custom_sync_url.text() == url
    assert prefs.login_status_updates == 1
    # and the key works for a sync
    from anki.sync import SyncAuth

    out = prefs.mw.col.sync_collection(SyncAuth(hkey=pm.profile["syncKey"], endpoint=url), False)
    assert out is not None


def test_use_for_this_profile_wrong_password(prefs, monkeypatch) -> None:
    group = make_tab(prefs)
    group.port.setValue(free_port())
    group.port.editingFinished.emit()
    group.enabled.setChecked(True)
    group.settings.password = "not-the-servers"  # e.g. changed elsewhere
    group.use_here.click()
    assert "failed" in prefs.warnings[-1]
    assert not prefs.mw.pm.profile.get("syncKey")


def test_delete_data(prefs, tmp_path) -> None:
    group = make_tab(prefs)
    group.port.setValue(free_port())
    group.port.editingFinished.emit()
    group.enabled.setChecked(True)
    folder = syncserver.user_folder(group.settings)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "junk"), "wb") as f:
        f.write(b"x" * 5000)
    group._update_storage()
    assert "KB" in group.storage.text() and group.delete.isEnabled()
    prefs.answers.append(False)
    group.delete.click()
    assert os.path.exists(os.path.join(folder, "junk"))
    group.delete.click()
    assert not os.path.exists(os.path.join(folder, "junk"))
    # it runs again afterwards, with empty databases of its own
    assert syncserver.status().running and syncserver.answers()
    assert not syncserver.has_data(group.settings)


# AnkiDroid's folder
######################################################################


@pytest.fixture
def droid_folder(tmp_path):
    folder = tmp_path / "AnkiDroid"
    os.makedirs(folder / "collection.media")
    Collection(str(folder / "collection.anki2")).close()
    return str(folder)


@pytest.fixture(autouse=True)
def folder_mode_offered(monkeypatch):
    monkeypatch.setattr(ankidroid, "FOLDER_READY", True)


def test_folder_mode_explained_until_ready(prefs, monkeypatch, droid_folder) -> None:
    monkeypatch.setattr(ankidroid, "FOLDER_READY", False)
    shown: list[str] = []
    monkeypatch.setattr("aqt.utils.showText", lambda text, **k: shown.append(text))
    group = droid_group(prefs)
    group.folder.setText(droid_folder)
    radio = group.radios[ankidroid.FOLDER]
    assert "not available" in radio.text()
    radio.click()
    # the popup says why and what to use instead; nothing changes
    assert len(shown) == 1 and "backups" in shown[0] and "AnkiDroid's media" in shown[0]
    assert group._mode == ankidroid.OFF and group.radios[ankidroid.OFF].isChecked()
    assert group.before_close() is None
    assert ankidroid.load(prefs.mw.pm.profile).mode == ankidroid.OFF


def test_folder_profile_shown_as_own_until_ready(prefs, monkeypatch, droid_folder) -> None:
    monkeypatch.setattr(ankidroid, "FOLDER_READY", False)
    ankidroid.store(prefs.mw.pm.profile, ankidroid.Source(mode=ankidroid.FOLDER, folder=droid_folder))
    group = droid_group(prefs)
    assert group.radios[ankidroid.OFF].isChecked()


def test_media_mode_warns_without_auto_sync(prefs, droid_folder) -> None:
    prefs.mw.pm.profile["autoSync"] = False
    group = droid_group(prefs)
    group.folder.setText(droid_folder)
    group.radios[ankidroid.MEDIA].click()
    assert "Automatic sync is off" in group.checks.text()


def droid_group(prefs):  # type: ignore[no-untyped-def]
    tab = advanced.AdvancedTab(prefs)
    tab.ankidroid = advanced.AnkiDroidGroup(tab)
    return tab.ankidroid


def test_ankidroid_off_by_default(prefs, platform) -> None:
    platform.versions = {"com.ichi2.anki": "2.25.3"}
    group = droid_group(prefs)
    assert group.radios[ankidroid.OFF].isChecked()
    assert not group.folder.isEnabled()
    assert "AnkiDroid 2.25.3" in group.checks.text()
    assert group.before_close() is None


def test_ankidroid_old_version_warns(prefs, platform) -> None:
    platform.versions = {"com.ichi2.anki": "2.19.1"}
    group = droid_group(prefs)
    assert "older than" in group.checks.text()


def test_ankidroid_choose_folder_mode(prefs, droid_folder) -> None:
    group = droid_group(prefs)
    group.folder.setText(droid_folder)
    group.radios[ankidroid.FOLDER].click()
    assert group._mode == ankidroid.FOLDER
    after = group.before_close()
    assert callable(after)
    saved = ankidroid.load(prefs.mw.pm.profile)
    assert saved.mode == ankidroid.FOLDER and saved.folder == droid_folder
    # media sync off: Preferences writes the checkbox into the profile
    assert not prefs.form.syncMedia.isChecked()


def test_ankidroid_declined_warning(prefs, droid_folder) -> None:
    group = droid_group(prefs)
    prefs.answers.append(False)
    group.radios[ankidroid.MEDIA].click()
    assert group._mode == ankidroid.OFF
    assert group.radios[ankidroid.OFF].isChecked()
    assert group.before_close() is None


def test_ankidroid_refused_when_unusable(prefs, platform, tmp_path) -> None:
    group = droid_group(prefs)
    group.folder.setText(str(tmp_path / "nothing here"))
    group.radios[ankidroid.MEDIA].click()
    assert group.before_close() is None
    assert "no folder" in prefs.warnings[-1]
    assert ankidroid.load(prefs.mw.pm.profile).mode == ankidroid.OFF
    assert prefs.form.syncMedia.isChecked()


def test_ankidroid_no_access(prefs, platform, droid_folder) -> None:
    platform.files_access = False
    group = droid_group(prefs)
    assert group.grant.isVisibleTo(group.box)
    group.folder.setText(droid_folder)
    group.radios[ankidroid.FOLDER].click()
    assert group.before_close() is None
    assert "All files access" in prefs.warnings[-1]


def test_ankidroid_media_mode_checks_sync(prefs, droid_folder) -> None:
    group = droid_group(prefs)
    group.folder.setText(droid_folder)
    group.radios[ankidroid.MEDIA].click()
    assert "isn't running" in group.checks.text()


def test_ankidroid_only_allow_delete_changed(prefs, droid_folder) -> None:
    ankidroid.store(prefs.mw.pm.profile, ankidroid.Source(mode=ankidroid.MEDIA, folder=droid_folder))
    group = droid_group(prefs)
    group.allow_delete.setChecked(True)
    # saved, but no need to reopen the profile
    assert group.before_close() is None
    assert ankidroid.load(prefs.mw.pm.profile).allow_delete_unused


def test_ankidroid_back_to_own(prefs, droid_folder) -> None:
    ankidroid.store(prefs.mw.pm.profile, ankidroid.Source(mode=ankidroid.FOLDER, folder=droid_folder))
    group = droid_group(prefs)
    group.radios[ankidroid.OFF].click()
    assert callable(group.before_close())
    assert ankidroid.load(prefs.mw.pm.profile).mode == ankidroid.OFF


def test_background_group_only_where_the_platform_has_it(prefs) -> None:
    tab = advanced.AdvancedTab(prefs)
    assert tab.background is None


def test_gamepad_group_only_where_the_platform_reads_controllers(prefs, platform, monkeypatch) -> None:
    # the Termux app's kioku_platform has no watch_gamepads: no Gamepad box
    assert not hasattr(platform, "watch_gamepads")
    assert advanced.AdvancedTab(prefs).gamepad is None
    monkeypatch.setattr(platform, "watch_gamepads", lambda listener: None, raising=False)
    group = advanced.AdvancedTab(prefs).gamepad
    assert group is not None and group.box.title() == "Gamepad"


def test_background_saved_and_applied(prefs, platform, monkeypatch) -> None:
    calls: list[bool] = []
    state = ["off"]
    monkeypatch.setattr(platform, "keep_running_in_background", calls.append, raising=False)
    monkeypatch.setattr(platform, "keep_running_in_background_status", lambda: state[0], raising=False)
    group = advanced.AdvancedTab(prefs).background
    assert group is not None and not group.enabled.isChecked()
    assert group.status.isHidden()
    prefs.answers.append(False)  # the warning declined
    group.enabled.setChecked(True)
    assert not group.enabled.isChecked() and calls == []
    assert not advanced.background_wanted(prefs.mw.pm.meta)
    state[0] = "asking"
    group.enabled.setChecked(True)
    assert calls == [True]
    assert "Waiting" in group.status.text()
    from aqt.profiles import ProfileManager

    saved = ProfileManager._unpickle(
        prefs.mw.pm, prefs.mw.pm.db.scalar("select data from profiles where name = '_global'")
    )
    assert advanced.background_wanted(saved)
    state[0] = "denied"
    group._refresh()
    assert "Settings app" in group.status.text()
    # next start: applied from the saved setting
    advanced.apply_background(prefs.mw)
    assert calls == [True, True]
    state[0] = "allowed"
    group.enabled.setChecked(False)
    assert calls[-1] is False and not advanced.background_wanted(prefs.mw.pm.meta)
    assert "Never" in group.status.text()
