package io.ankidesk.kioku;

import android.os.SystemClock;
import android.view.InputDevice;
import android.view.KeyCharacterMap;
import android.view.KeyEvent;
import android.view.View;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * A hardware keyboard's keys reach Anki's shortcuts after a page was tapped.
 *
 * A tap on a page (the card, the review screen's buttons) gives its WebView
 * Android's focus, and the WebView took every key: Space, Enter and 1-4 never
 * reached Qt, so the reviewer ignored the keyboard. Qt's own window keeps
 * Qt's focus meanwhile, so a key pressed outside a text field in a page now
 * goes to Qt first, through Qt's onKeyDown as if Qt's view had the focus.
 * One that no shortcut takes reaches the web view widget, and Python
 * (webengine.QWebEngineView.keyPressEvent) hands it back with toPage(): the
 * page then gets it, as with desktop Anki's web views and on iOS (keys.py).
 * A text field in a page keeps every key.
 */
final class KiokuKeys {
    private KiokuKeys() {
    }

    /** The last key press sent to Qt, until Python hands it back or the next one. */
    private static KeyEvent pending;
    private static KiokuBridge.Page pendingPage;
    /** Whether pending's release went to Qt before Python handed it back. */
    private static boolean pendingReleased;
    /** The key whose press went to the page: its release goes there too. */
    private static int toPageCode = -1;
    private static KiokuBridge.Page toPagePage;

    /** From KiokuActivity.dispatchKeyEvent, after the gamepad: true if taken. */
    static boolean onKey(KeyEvent e) {
        int action = e.getAction();
        if (action == KeyEvent.ACTION_UP && e.getKeyCode() == toPageCode) {
            KiokuBridge.Page p = toPagePage;
            toPageCode = -1;
            toPagePage = null;
            return p != null && p.view.dispatchKeyEvent(e);
        }
        if (action == KeyEvent.ACTION_DOWN) {
            // a press Qt gets from its own view mustn't hand back an older one
            pending = null;
            pendingPage = null;
        }
        if (action != KeyEvent.ACTION_DOWN && action != KeyEvent.ACTION_UP) {
            return false;
        }
        if (e.isSystem() || (e.getSource() & InputDevice.SOURCE_KEYBOARD) != InputDevice.SOURCE_KEYBOARD) {
            return false;
        }
        View focus = KiokuBridge.activity.getCurrentFocus();
        KiokuBridge.Page page = KiokuBridge.pageOf(focus);
        if (page == null || page.editing) {
            return false;
        }
        if (action == KeyEvent.ACTION_DOWN) {
            pending = new KeyEvent(e);
            pendingPage = page;
            pendingReleased = false;
            return ((KiokuActivity) KiokuBridge.activity).qtKey(e);
        }
        if (pending != null && pending.getKeyCode() == e.getKeyCode()) {
            pendingReleased = true;
        }
        return ((KiokuActivity) KiokuBridge.activity).qtKey(e);
    }

    /**
     * From Python (keys.toPage): Qt took no shortcut for the last key press,
     * whose text Qt saw as text. Another press (typed meanwhile) or a stale
     * one stays with Qt.
     */
    static void toPage(String text) {
        KeyEvent e = pending;
        KiokuBridge.Page page = pendingPage;
        pending = null;
        pendingPage = null;
        if (e == null || page == null || SystemClock.uptimeMillis() - e.getEventTime() > 2000) {
            return;
        }
        int c = e.getUnicodeChar();
        // printable keys only: Qt reads Enter as "\r", Android as '\n'
        if (c >= 0x20 && !text.isEmpty() && text.charAt(0) >= 0x20
                && !text.equals(new String(Character.toChars(c)))) {
            return;
        }
        page.view.dispatchKeyEvent(e);
        if (pendingReleased) {
            page.view.dispatchKeyEvent(KeyEvent.changeAction(e, KeyEvent.ACTION_UP));
        } else {
            toPageCode = e.getKeyCode();
            toPagePage = page;
        }
    }

    /**
     * For the in-app tests: a hardware keyboard's key, through
     * KiokuActivity's dispatch like a real one. {"code", "down", "meta"}.
     * Returns whether the activity took it.
     */
    static boolean test(JSONObject a) throws JSONException {
        long now = SystemClock.uptimeMillis();
        KeyEvent e = new KeyEvent(now, now,
                a.getBoolean("down") ? KeyEvent.ACTION_DOWN : KeyEvent.ACTION_UP,
                a.getInt("code"), 0, a.optInt("meta"), KeyCharacterMap.VIRTUAL_KEYBOARD, 0, 0,
                InputDevice.SOURCE_KEYBOARD);
        return KiokuBridge.activity.dispatchKeyEvent(e);
    }
}
