package io.ankidesk.kioku;

import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.system.ErrnoException;
import android.system.Os;
import android.util.Log;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.WindowInsets;

import org.qtproject.qt.android.bindings.QtActivity;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Unpacks the Python runtime (standard library, Anki, Kioku's Python code;
 * assets/python.zip) on the first start after an install or update, then
 * starts Qt, whose main() (src/main.cpp) runs Python.
 */
public class KiokuActivity extends QtActivity {
    private static final String TAG = "Kioku";
    /** A kioku:// link from KiokuLinkActivity */
    static final String EXTRA_LINK = "io.ankidesk.kioku.LINK";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        KiokuBridge.activity = this;
        File python = new File(getFilesDir(), "python");
        try {
            unpackIfNeeded(python);
            Os.setenv("KIOKU_PYTHON_HOME", python.getAbsolutePath(), true);
            Os.setenv("HOME", getFilesDir().getAbsolutePath(), true);
            Os.setenv("TMPDIR", getCacheDir().getAbsolutePath(), true);
            File external = getExternalFilesDir(null);
            Os.setenv("KIOKU_DOCUMENTS", (external != null ? external : getFilesDir()).getAbsolutePath(), true);
            // tools/run_device.sh: am start --ez dev true
            if (getIntent() != null && getIntent().getBooleanExtra("dev", false)) {
                Os.setenv("KIOKU_DEV", "1", true);
            }
        } catch (IOException | ErrnoException e) {
            Log.e(TAG, "preparing the Python runtime failed", e);
        }
        // Qt hands a VIEW intent to QDesktopServices once it runs. Not when
        // Android brings the activity back after the process died: the
        // link was followed then already
        boolean restored = savedInstanceState != null
                || (getIntent().getFlags() & Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY) != 0;
        if (!restored) {
            setIntent(linkIntent(getIntent()));
        }
        super.onCreate(savedInstanceState);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(linkIntent(intent));
    }

    /** A link from KiokuLinkActivity as the VIEW intent Qt expects. */
    private static Intent linkIntent(Intent intent) {
        String link = intent == null ? null : intent.getStringExtra(EXTRA_LINK);
        return link == null ? intent : new Intent(Intent.ACTION_VIEW, Uri.parse(link));
    }

    private void unpackIfNeeded(File target) throws IOException {
        String stamp;
        try {
            PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
            stamp = info.versionCode + ":" + info.lastUpdateTime;
        } catch (Exception e) {
            stamp = "unknown";
        }
        File stampFile = new File(target, ".stamp");
        if (stampFile.exists() && stamp.equals(new String(Files.readAllBytes(stampFile.toPath())))) {
            return;
        }
        long start = System.currentTimeMillis();
        deleteRecursively(target);
        byte[] buffer = new byte[1 << 16];
        try (InputStream in = getAssets().open("python.zip");
             ZipInputStream zip = new ZipInputStream(in)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                File out = new File(target, entry.getName());
                if (!out.getCanonicalPath().startsWith(target.getCanonicalPath())) {
                    throw new IOException("bad zip entry " + entry.getName());
                }
                if (entry.isDirectory()) {
                    out.mkdirs();
                    continue;
                }
                out.getParentFile().mkdirs();
                try (FileOutputStream os = new FileOutputStream(out)) {
                    int n;
                    while ((n = zip.read(buffer)) > 0) {
                        os.write(buffer, 0, n);
                    }
                }
            }
        }
        Files.write(stampFile.toPath(), stamp.getBytes());
        Log.i(TAG, "unpacked Python runtime in " + (System.currentTimeMillis() - start) + " ms");
    }

    private static void deleteRecursively(File f) {
        File[] children = f.listFiles();
        if (children != null) {
            for (File c : children) {
                deleteRecursively(c);
            }
        }
        f.delete();
    }

    // gamepads go to kioku.gamepad (KiokuGamepad), not to Qt or a web view
    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        return KiokuGamepad.onKey(event) || super.dispatchKeyEvent(event);
    }

    @Override
    public boolean dispatchGenericMotionEvent(MotionEvent event) {
        return KiokuGamepad.onMotion(event) || super.dispatchGenericMotionEvent(event);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        // Qt's version calls QtWindowInsetsController.restoreFullScreenVisibility(),
        // which on Android 11+ takes the bars hidden by another app's popup (the
        // "Open with" chooser) for full screen and hides them for good. Kioku
        // is never full screen: show the bars instead. (Activity's own
        // onWindowFocusChanged does nothing.)
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            super.onWindowFocusChanged(hasFocus);
        } else if (hasFocus) {
            getWindow().getInsetsController().show(WindowInsets.Type.systemBars());
        }
    }

    // KiokuBridge.lifecycle: a profile on AnkiDroid's collection closes it
    // in the background
    @Override
    protected void onPause() {
        KiokuBridge.lifecycle("pause");
        super.onPause();
    }

    @Override
    protected void onStop() {
        KiokuBridge.lifecycle("stop");
        super.onStop();
    }

    @Override
    protected void onResume() {
        KiokuBridge.lifecycle("resume");
        super.onResume();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        KiokuBridge.lifecycle("resume");
        if (!KiokuBridge.onRequestPermissionsResult(requestCode, grantResults)) {
            super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        KiokuBridge.lifecycle("resume");
        if (!KiokuBridge.onActivityResult(requestCode, resultCode, data)) {
            super.onActivityResult(requestCode, resultCode, data);
        }
    }
}
