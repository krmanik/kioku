package io.ankidesk.kioku;

import android.content.Context;
import android.hardware.input.InputManager;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.InputDevice;
import android.view.KeyCharacterMap;
import android.view.KeyEvent;
import android.view.MotionEvent;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.Iterator;

/**
 * Gamepads and game controllers for kioku.gamepad (Python): while watched,
 * their buttons, sticks, triggers and hat switch go to Python as
 * gamepadButton, gamepadAxes and gamepadDevice events instead of to Qt and
 * the web views. Keyboards, a TV remote's d-pad and Back keep their usual
 * way.
 */
final class KiokuGamepad {
    private static volatile boolean watching;
    private static InputManager.InputDeviceListener deviceListener;
    /** Last axes sent: lx, ly, rx, ry, hx, hy, lt, rt (tenths) */
    private static final int[] sent = new int[8];

    private KiokuGamepad() {
    }

    static void watch(boolean on) {
        watching = on;
        new Handler(Looper.getMainLooper()).post(() -> watchDevices(on));
    }

    private static void watchDevices(boolean on) {
        InputManager input = (InputManager) KiokuBridge.activity.getSystemService(Context.INPUT_SERVICE);
        if (input == null) {
            return;
        }
        if (!on) {
            if (deviceListener != null) {
                input.unregisterInputDeviceListener(deviceListener);
                deviceListener = null;
            }
            return;
        }
        if (deviceListener == null) {
            deviceListener = new InputManager.InputDeviceListener() {
                @Override
                public void onInputDeviceAdded(int id) {
                    device(InputDevice.getDevice(id), id, true);
                }

                @Override
                public void onInputDeviceRemoved(int id) {
                    device(null, id, false);
                }

                @Override
                public void onInputDeviceChanged(int id) {
                }
            };
            input.registerInputDeviceListener(deviceListener, null);
        }
        for (int id : InputDevice.getDeviceIds()) {
            device(InputDevice.getDevice(id), id, true);
        }
    }

    private static boolean isGamepad(InputDevice d) {
        if (d == null || d.isVirtual()) {
            return false;
        }
        int s = d.getSources();
        return (s & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD
                || (s & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK;
    }

    private static final java.util.Map<Integer, String> devices = new java.util.HashMap<>();

    private static void device(InputDevice d, int id, boolean added) {
        if (added) {
            if (!isGamepad(d) || devices.containsKey(id)) {
                return;
            }
            devices.put(id, d.getName());
            KiokuBridge.event(KiokuBridge.obj("type", "gamepadDevice", "id", String.valueOf(id),
                    "name", d.getName(), "connected", true));
        } else {
            String name = devices.remove(id);
            if (name != null) {
                KiokuBridge.event(KiokuBridge.obj("type", "gamepadDevice", "id", String.valueOf(id),
                        "name", name, "connected", false));
            }
        }
    }

    private static boolean fromGamepad(int source) {
        return (source & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD
                || (source & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK;
    }

    /** kioku.gamepad's button names (by position: A is the bottom one). */
    private static String button(int keyCode) {
        switch (keyCode) {
            case KeyEvent.KEYCODE_BUTTON_A:
            case KeyEvent.KEYCODE_DPAD_CENTER:
                return "A";
            case KeyEvent.KEYCODE_BUTTON_B:
                return "B";
            case KeyEvent.KEYCODE_BUTTON_X:
                return "X";
            case KeyEvent.KEYCODE_BUTTON_Y:
                return "Y";
            case KeyEvent.KEYCODE_BUTTON_L1:
                return "L1";
            case KeyEvent.KEYCODE_BUTTON_R1:
                return "R1";
            case KeyEvent.KEYCODE_BUTTON_L2:
                return "L2";
            case KeyEvent.KEYCODE_BUTTON_R2:
                return "R2";
            case KeyEvent.KEYCODE_BUTTON_THUMBL:
                return "L3";
            case KeyEvent.KEYCODE_BUTTON_THUMBR:
                return "R3";
            case KeyEvent.KEYCODE_BUTTON_START:
                return "Menu";
            case KeyEvent.KEYCODE_BUTTON_SELECT:
                return "View";
            case KeyEvent.KEYCODE_DPAD_UP:
                return "Up";
            case KeyEvent.KEYCODE_DPAD_DOWN:
                return "Down";
            case KeyEvent.KEYCODE_DPAD_LEFT:
                return "Left";
            case KeyEvent.KEYCODE_DPAD_RIGHT:
                return "Right";
            default:
                return null;
        }
    }

    /** From KiokuActivity.dispatchKeyEvent: true if taken. */
    static boolean onKey(KeyEvent e) {
        if (!watching) {
            return false;
        }
        int code = e.getKeyCode();
        boolean gamepadButton = KeyEvent.isGamepadButton(code);
        if (!gamepadButton && !fromGamepad(e.getSource())) {
            return false;
        }
        String name = button(code);
        if (name == null) {
            // Home/Mode, Back, volume: the system's
            return false;
        }
        if (e.getAction() == KeyEvent.ACTION_DOWN) {
            if (e.getRepeatCount() == 0) {
                KiokuBridge.event(KiokuBridge.obj("type", "gamepadButton", "button", name, "pressed", true));
            }
        } else if (e.getAction() == KeyEvent.ACTION_UP) {
            KiokuBridge.event(KiokuBridge.obj("type", "gamepadButton", "button", name, "pressed", false));
        }
        return true;
    }

    private static int tenths(float v) {
        return Math.round(v * 10);
    }

    /** From KiokuActivity.dispatchGenericMotionEvent: true if taken. */
    static boolean onMotion(MotionEvent e) {
        if (!watching || e.getAction() != MotionEvent.ACTION_MOVE
                || (e.getSource() & InputDevice.SOURCE_JOYSTICK) != InputDevice.SOURCE_JOYSTICK) {
            return false;
        }
        int[] now = {
                tenths(e.getAxisValue(MotionEvent.AXIS_X)),
                tenths(e.getAxisValue(MotionEvent.AXIS_Y)),
                tenths(e.getAxisValue(MotionEvent.AXIS_Z)),
                tenths(e.getAxisValue(MotionEvent.AXIS_RZ)),
                tenths(e.getAxisValue(MotionEvent.AXIS_HAT_X)),
                tenths(e.getAxisValue(MotionEvent.AXIS_HAT_Y)),
                tenths(Math.max(e.getAxisValue(MotionEvent.AXIS_LTRIGGER), e.getAxisValue(MotionEvent.AXIS_BRAKE))),
                tenths(Math.max(e.getAxisValue(MotionEvent.AXIS_RTRIGGER), e.getAxisValue(MotionEvent.AXIS_GAS))),
        };
        if (java.util.Arrays.equals(now, sent)) {
            return true;
        }
        System.arraycopy(now, 0, sent, 0, now.length);
        KiokuBridge.event(KiokuBridge.obj("type", "gamepadAxes",
                "lx", now[0] / 10.0, "ly", now[1] / 10.0, "rx", now[2] / 10.0, "ry", now[3] / 10.0,
                "hx", now[4] / 10.0, "hy", now[5] / 10.0, "lt", now[6] / 10.0, "rt", now[7] / 10.0));
        return true;
    }

    /**
     * For the in-app tests: an event as a controller sends it, through
     * KiokuActivity's dispatch like a real one. {"kind": "key", "code",
     * "down", "source"} or {"kind": "motion", "axes": {"AXIS_X": 0.5, ...}}.
     * A key from another source is only offered to onKey (never to Qt).
     * Returns whether Kioku took it.
     */
    static boolean test(JSONObject a) throws JSONException {
        long now = SystemClock.uptimeMillis();
        if (a.getString("kind").equals("key")) {
            int source = a.getInt("source");
            int code = a.getInt("code");
            KeyEvent e = new KeyEvent(now, now,
                    a.getBoolean("down") ? KeyEvent.ACTION_DOWN : KeyEvent.ACTION_UP,
                    code, 0, 0, KeyCharacterMap.VIRTUAL_KEYBOARD, 0, 0, source);
            if (fromGamepad(source) || KeyEvent.isGamepadButton(code)) {
                return KiokuBridge.activity.dispatchKeyEvent(e);
            }
            return onKey(e);
        }
        MotionEvent.PointerProperties props = new MotionEvent.PointerProperties();
        props.id = 0;
        props.toolType = MotionEvent.TOOL_TYPE_UNKNOWN;
        MotionEvent.PointerCoords coords = new MotionEvent.PointerCoords();
        JSONObject axes = a.getJSONObject("axes");
        for (Iterator<String> it = axes.keys(); it.hasNext(); ) {
            String name = it.next();
            coords.setAxisValue(MotionEvent.axisFromString(name), (float) axes.getDouble(name));
        }
        MotionEvent m = MotionEvent.obtain(now, now, MotionEvent.ACTION_MOVE, 1,
                new MotionEvent.PointerProperties[]{props}, new MotionEvent.PointerCoords[]{coords},
                0, 0, 1f, 1f, 0, 0, InputDevice.SOURCE_JOYSTICK, 0);
        try {
            return KiokuBridge.activity.dispatchGenericMotionEvent(m);
        } finally {
            m.recycle();
        }
    }
}
