package io.ankidesk.kioku;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.pdf.PdfRenderer;
import android.graphics.pdf.content.PdfPageTextContent;
import android.graphics.Insets;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import android.util.Log;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.widget.Toast;
import android.webkit.ConsoleMessage;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.JsResult;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.webkit.ScriptHandler;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

/**
 * Everything Kioku's Python code needs from Android (python/kioku_platform),
 * reached through the _kioku_android module (src/kioku_android.cpp):
 *
 *   call(method, json args) -> String     from Python (Qt's thread)
 *   nativeEvent(json)                     to Python, delivered on Qt's thread
 *   nativeRequest(json, ms) -> String     to Python, waiting up to ms for the
 *                                         answer (null without one)
 *
 * Web views stand in for Qt WebEngine; file picking copies the chosen files
 * into the app (Python cannot open content:// URIs); MediaPlayer plays card
 * audio (Python cannot start mpv) and TextToSpeech speaks {{tts}}.
 */
public class KiokuBridge {
    private static final String TAG = "Kioku";
    private static final int PICK_FILES = 0x6b69;

    static Activity activity;
    private static final Handler ui = new Handler(Looper.getMainLooper());
    private static final Map<Integer, Page> pages = new ConcurrentHashMap<>();
    private static final Map<Integer, PdfRenderer> pdfs = new ConcurrentHashMap<>();
    private static int nextPdf = 1;
    private static MediaPlayer player;
    private static volatile TextToSpeech tts;

    /** Implemented in src/kioku_android.cpp. */
    static native void nativeEvent(String json);
    static native String nativeRequest(String json, int timeoutMs);
    private static native boolean nativeLockUi();
    private static native void nativeUnlockUi();
    private static native void nativeAnswerUi();

    private static void event(JSONObject json) {
        try {
            nativeEvent(json.toString());
        } catch (UnsatisfiedLinkError e) {
            Log.w(TAG, "event before the native side was ready: " + json);
        }
    }

    /** Python's answer, or null if none came within timeoutMs. */
    private static String request(JSONObject json, int timeoutMs) {
        try {
            return nativeRequest(json.toString(), timeoutMs);
        } catch (UnsatisfiedLinkError e) {
            return null;
        }
    }

    private static JSONObject obj(Object... keyValues) {
        JSONObject o = new JSONObject();
        try {
            for (int i = 0; i < keyValues.length; i += 2) {
                o.put((String) keyValues[i], keyValues[i + 1]);
            }
        } catch (JSONException e) {
            throw new RuntimeException(e);
        }
        return o;
    }

    private static <T> T onUiThread(Callable<T> work) throws Exception {
        if (Looper.myLooper() == Looper.getMainLooper()) {
            return work.call();
        }
        // Qt's deadlock protector (src/kioku_android.cpp): while it is held,
        // the UI thread's keyboard and accessibility queries give up instead
        // of waiting for Qt's thread. If a query holds it, answer it and retry.
        boolean locked;
        int tries = 0;
        while (!(locked = nativeLockUi()) && ++tries < 5000) {
            nativeAnswerUi();
            Thread.sleep(1);
        }
        if (!locked) {
            Log.w(TAG, "waiting for the UI thread without the deadlock protector");
        }
        try {
            FutureTask<T> task = new FutureTask<>(work);
            ui.post(task);
            return task.get();
        } finally {
            if (locked) {
                nativeUnlockUi();
            }
        }
    }

    /** The entry point for Python. Returns a JSON value or "null". */
    public static String call(String method, String argsJson) {
        try {
            JSONObject a = new JSONObject(argsJson);
            Object result = dispatch(method, a);
            if (result == null) {
                return "null";
            }
            // wrap() leaves strings as they are, which is not JSON
            return result instanceof String ? JSONObject.quote((String) result)
                    : JSONObject.wrap(result).toString();
        } catch (Throwable e) {
            Log.e(TAG, "call " + method + " failed", e);
            return obj("error", e.toString()).toString();
        }
    }

    private static Object dispatch(String method, JSONObject a) throws Exception {
        switch (method) {
            case "webview.create": {
                int id = a.getInt("id");
                onUiThread(() -> pages.put(id, new Page(id)));
                return true;
            }
            case "webview.url":
                return onUiThread(() -> page(a).view.getUrl());
            case "webview.title":
                return onUiThread(() -> page(a).view.getTitle());
            case "webview.history":
                return onUiThread(() -> {
                    android.webkit.WebBackForwardList list = page(a).view.copyBackForwardList();
                    int i = list.getCurrentIndex();
                    return obj("back", i > 0 ? list.getItemAtIndex(i - 1).getUrl() : "",
                            "forward", i >= 0 && i + 1 < list.getSize()
                                    ? list.getItemAtIndex(i + 1).getUrl() : "");
                });
            case "darkMode":
                return (activity.getResources().getConfiguration().uiMode
                        & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
            case "density":
                return activity.getResources().getDisplayMetrics().density;
            case "tts.voices":
                // starts the engine, waiting for the UI thread: not from it
                return ttsVoices();
            case "storage.allFiles":
                return allFilesAccess();
            case "apps.versions":
                return appVersions(a.getJSONArray("packages"));
            case "lifecycle.watch":
                watchLifecycle = a.getBoolean("on");
                return true;
            // PDFs for PyQt6.QtPdf, from Python's worker threads
            case "pdf.open":
                return pdfOpen(a.getString("path"));
            case "pdf.text":
                return pdfText(a.getInt("id"), a.getInt("page"));
            case "pdf.render":
                return pdfRender(a.getInt("id"), a.getInt("page"), a.getInt("width"),
                        a.getInt("height"), a.getString("out"));
            case "pdf.close": {
                PdfRenderer r = pdfs.remove(a.getInt("id"));
                if (r != null) {
                    synchronized (r) {
                        r.close();
                    }
                }
                return true;
            }
        }
        // everything else runs on the UI thread without waiting
        ui.post(() -> {
            try {
                dispatchAsync(method, a);
            } catch (Exception e) {
                Log.e(TAG, "call " + method + " failed", e);
            }
        });
        return null;
    }

    private static Page page(JSONObject a) throws JSONException {
        Page p = pages.get(a.getInt("id"));
        if (p == null) {
            throw new IllegalStateException("no web view " + a.getInt("id"));
        }
        return p;
    }

    /** CookieManager can't delete one domain's cookies: expire the ones it
     * sends to that domain, host-only and domain-wide (it keeps both kinds). */
    private static void deleteCookies(String domain, String name) {
        CookieManager cookies = CookieManager.getInstance();
        String host = domain.startsWith(".") ? domain.substring(1) : domain;
        String url = "https://" + host + "/";
        String all = cookies.getCookie(url);
        if (all == null) {
            return;
        }
        for (String pair : all.split(";")) {
            String n = pair.trim().split("=", 2)[0];
            if (n.isEmpty() || !(name.isEmpty() || name.equals(n))) {
                continue;
            }
            String expired = n + "=; Max-Age=0; Path=/";
            cookies.setCookie(url, expired);
            cookies.setCookie(url, expired + "; Domain=" + host);
        }
        cookies.flush();
    }

    private static void dispatchAsync(String method, JSONObject a) throws Exception {
        switch (method) {
            case "webview.scripts":
                page(a).setScripts(a.getJSONArray("scripts"));
                break;
            case "webview.load": {
                Map<String, String> headers = new HashMap<>();
                JSONObject h = a.optJSONObject("headers");
                if (h != null) {
                    for (java.util.Iterator<String> it = h.keys(); it.hasNext(); ) {
                        String k = it.next();
                        headers.put(k, h.getString(k));
                    }
                }
                page(a).load(a.getString("url"), headers);
                break;
            }
            case "webview.html":
                page(a).generation++;
                page(a).view.loadDataWithBaseURL(a.optString("base", null), a.getString("html"),
                        "text/html", "utf-8", null);
                break;
            case "webview.eval": {
                Page p = page(a);
                int cb = a.optInt("cb", 0);
                p.view.evaluateJavascript(a.getString("js"), value -> {
                    if (cb != 0) {
                        event(obj("type", "eval", "id", p.id, "cb", cb, "value", value));
                    }
                });
                break;
            }
            case "webview.reply":
                page(a).view.evaluateJavascript("window.__kiokuResolve(" + a.getInt("call") + ","
                        + a.getBoolean("ok") + "," + JSONObject.quote(a.getString("value")) + ")", null);
                break;
            case "webview.pdf": {
                Page p = page(a);
                String path = a.getString("path");
                android.print.KiokuPdfWriter.write(p.view.createPrintDocumentAdapter("Kioku"),
                        new File(path), ok -> event(obj("type", "pdf", "id", p.id, "path", path, "ok", ok)));
                break;
            }
            case "webview.confirmResult":
                page(a).answerConfirm(a.getInt("token"), a.getBoolean("ok"));
                break;
            case "webview.background":
                page(a).view.setBackgroundColor((int) a.getLong("argb"));
                break;
            case "webview.zoom":
                page(a).view.getSettings().setTextZoom((int) Math.round(a.getDouble("factor") * 100));
                break;
            case "webview.keyboardInsets": {
                Page p = page(a);
                p.keyboardInsets = a.getBoolean("on");
                p.view.requestApplyInsets();
                break;
            }
            case "webview.reload":
                page(a).generation++;
                page(a).view.reload();
                break;
            case "webview.stop":
                page(a).view.stopLoading();
                break;
            case "webview.back":
                page(a).view.goBack();
                break;
            case "webview.forward":
                page(a).view.goForward();
                break;
            case "cookies.set": {
                CookieManager cookies = CookieManager.getInstance();
                cookies.setCookie(a.getString("url"), a.getString("cookie"));
                cookies.flush();
                break;
            }
            case "cookies.delete":
                deleteCookies(a.getString("domain"), a.getString("name"));
                break;
            case "webview.destroy": {
                Page p = pages.remove(a.getInt("id"));
                if (p != null) {
                    p.view.destroy();
                }
                break;
            }
            case "openUrl":
                try {
                    activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(a.getString("url"))));
                } catch (ActivityNotFoundException e) {
                    Log.w(TAG, "nothing opens " + a.getString("url"));
                }
                break;
            case "pickFiles":
                pickFiles(a.optBoolean("multi"), a.optString("mime", "*/*"));
                break;
            case "moveTaskToBack":
                activity.moveTaskToBack(true);
                break;
            case "syncService":
                syncService(a.getBoolean("running"), a.optString("text"));
                break;
            case "storage.requestAllFiles":
                requestAllFilesAccess();
                break;
            case "apps.details":
                activity.startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.parse("package:" + a.getString("package"))));
                break;
            case "apps.launch": {
                Intent launch = activity.getPackageManager().getLaunchIntentForPackage(a.getString("package"));
                if (launch != null) {
                    activity.startActivity(launch);
                }
                break;
            }
            case "keepAwake":
                activity.getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                break;
            case "audio.play":
                playAudio(a.getString("path"));
                break;
            case "audio.stop":
                stopAudio();
                break;
            case "audio.pause":
                if (player != null) {
                    if (player.isPlaying()) {
                        player.pause();
                    } else {
                        player.start();
                    }
                }
                break;
            case "audio.seek":
                if (player != null) {
                    player.seekTo(Math.max(0, player.getCurrentPosition() + a.getInt("ms")));
                }
                break;
            case "tts.speak":
                speak(a.getString("text"), a.getString("voice"), a.getDouble("rate"), a.getInt("id"));
                break;
            case "tts.stop":
                if (tts != null) {
                    tts.stop();
                }
                break;
            default:
                Log.w(TAG, "unknown call " + method);
        }
    }

    /** For QWindow::fromWinId(): the View to embed into a Qt widget. */
    public static View getView(int id) {
        Page p = pages.get(id);
        return p == null ? null : p.view;
    }

    // Files ------------------------------------------------------------------

    private static void pickFiles(boolean multi, String mime) {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType(mime);
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, multi);
        activity.startActivityForResult(intent, PICK_FILES);
    }

    static boolean onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode != PICK_FILES) {
            return false;
        }
        List<Uri> uris = new ArrayList<>();
        if (resultCode == Activity.RESULT_OK && data != null) {
            ClipData clip = data.getClipData();
            if (clip != null) {
                for (int i = 0; i < clip.getItemCount(); i++) {
                    uris.add(clip.getItemAt(i).getUri());
                }
            } else if (data.getData() != null) {
                uris.add(data.getData());
            }
        }
        // copying can take a while (decks are large): not on the UI thread
        new Thread(() -> {
            JSONArray paths = new JSONArray();
            File dir = new File(activity.getCacheDir(), "picked/" + System.currentTimeMillis());
            dir.mkdirs();
            for (Uri uri : uris) {
                try {
                    File out = new File(dir, displayName(uri));
                    try (InputStream in = activity.getContentResolver().openInputStream(uri);
                         OutputStream os = new FileOutputStream(out)) {
                        byte[] buffer = new byte[1 << 16];
                        int n;
                        while ((n = in.read(buffer)) > 0) {
                            os.write(buffer, 0, n);
                        }
                    }
                    paths.put(out.getAbsolutePath());
                } catch (Exception e) {
                    Log.e(TAG, "copying " + uri + " failed", e);
                }
            }
            event(obj("type", "picked", "paths", paths));
        }).start();
        return true;
    }

    private static String displayName(Uri uri) {
        try (Cursor c = activity.getContentResolver().query(uri,
                new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                String name = c.getString(0);
                if (name != null && !name.isEmpty()) {
                    return name.replace('/', '_');
                }
            }
        } catch (Exception ignored) {
        }
        return "file";
    }

    // Shared storage (AnkiDroid's folder) ------------------------------------

    private static final int STORAGE_PERMISSION = 0x6b66;

    private static boolean allFilesAccess() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            return Environment.isExternalStorageManager();
        }
        return activity.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED;
    }

    private static void requestAllFilesAccess() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                activity.startActivity(new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                        Uri.parse("package:" + activity.getPackageName())));
            } catch (ActivityNotFoundException e) {
                activity.startActivity(new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION));
            }
        } else {
            activity.requestPermissions(new String[]{Manifest.permission.READ_EXTERNAL_STORAGE,
                    Manifest.permission.WRITE_EXTERNAL_STORAGE}, STORAGE_PERMISSION);
        }
    }

    /** {package: versionName} for the installed ones of `packages`. */
    private static JSONObject appVersions(JSONArray packages) throws JSONException {
        JSONObject found = new JSONObject();
        PackageManager pm = activity.getPackageManager();
        for (int i = 0; i < packages.length(); i++) {
            String name = packages.getString(i);
            try {
                PackageInfo info = pm.getPackageInfo(name, 0);
                found.put(name, info.versionName != null ? info.versionName : "");
            } catch (PackageManager.NameNotFoundException ignored) {
            }
        }
        return found;
    }

    // Sync server ------------------------------------------------------------

    private static final int NOTIFICATION_PERMISSION = 0x6b6e;
    private static boolean syncRunning;
    private static String syncText = "";

    private static void syncService(boolean running, String text) {
        syncRunning = running;
        syncText = text;
        if (running && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            // without it the service still runs, just without its notification
            activity.requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},
                    NOTIFICATION_PERMISSION);
        }
        KiokuSyncService.update(activity, running, text);
    }

    /** The service posted its notification before the permission was
     * granted, which hides it: post it again. */
    static boolean onRequestPermissionsResult(int requestCode, int[] grantResults) {
        if (requestCode == STORAGE_PERMISSION) {
            return true;
        }
        if (requestCode != NOTIFICATION_PERMISSION) {
            return false;
        }
        if (syncRunning && grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            KiokuSyncService.update(activity, true, syncText);
        }
        return true;
    }

    /** The notification's Stop action. */
    static void syncServerStopRequested() {
        event(obj("type", "syncServiceStop"));
    }

    // Going to the background (a profile on AnkiDroid's collection) -------

    private static volatile boolean watchLifecycle;
    // AnkiDroid's activity resumes only after Kioku's onPause returns, but
    // its onStop comes later; past this, Android resumes it anyway
    private static final int PAUSE_WAIT_MS = 400;
    // after onStop Qt's event loop no longer runs until Kioku is back
    private static final int STOP_WAIT_MS = 1500;

    private static long pausedAt;

    /** From KiokuActivity, before Qt hears of the change. On pause and stop,
     * waits for Python (kioku.background) to close AnkiDroid's collection or
     * to send its changes to the sync server; on resume (and the activity and
     * permission results that come just before it) tells Python, ahead of
     * anything else that reaches it. */
    static void lifecycle(String state) {
        if (state.equals("pause")) {
            pausedAt = System.currentTimeMillis();
        }
        if (!watchLifecycle) {
            return;
        }
        if (state.equals("resume")) {
            long away = pausedAt == 0 ? 0 : System.currentTimeMillis() - pausedAt;
            pausedAt = 0;
            event(obj("type", "foreground", "away_ms", away));
            return;
        }
        int waitMs = state.equals("pause") ? PAUSE_WAIT_MS : STOP_WAIT_MS;
        long deadline = System.currentTimeMillis() + waitMs;
        String answer = null;
        long start = System.currentTimeMillis();
        while (true) {
            long left = deadline - System.currentTimeMillis();
            if (left <= 0) {
                break;
            }
            answer = request(obj("type", "background", "state", state), (int) left);
            // "busy": an operation is finishing; Qt's thread gets to handle
            // its completion between two requests. "wait": a sync is running
            if (answer == null || !(answer.equals("busy") || answer.equals("wait"))) {
                break;
            }
            try {
                Thread.sleep(20);
            } catch (InterruptedException e) {
                break;
            }
        }
        Log.i(TAG, "background " + state + ": " + answer + " in "
                + (System.currentTimeMillis() - start) + " ms");
        if (state.equals("stop") && "busy".equals(answer)) {
            Toast.makeText(activity, "Kioku is still busy with AnkiDroid's collection, so AnkiDroid "
                    + "can't open it until you go back to Kioku.", Toast.LENGTH_LONG).show();
        }
    }

    // PDFs -------------------------------------------------------------------

    /** {"id", "sizes": [[width, height] in points, ...]} or {"fail": missing|format|password} */
    private static Object pdfOpen(String path) throws Exception {
        File file = new File(path);
        if (!file.isFile()) {
            return obj("fail", "missing");
        }
        ParcelFileDescriptor fd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
        PdfRenderer r;
        try {
            r = new PdfRenderer(fd);
        } catch (SecurityException e) {
            fd.close();
            return obj("fail", "password");
        } catch (java.io.IOException e) {
            fd.close();
            return obj("fail", "format");
        }
        JSONArray sizes = new JSONArray();
        for (int i = 0; i < r.getPageCount(); i++) {
            try (PdfRenderer.Page page = r.openPage(i)) {
                sizes.put(new JSONArray().put(page.getWidth()).put(page.getHeight()));
            }
        }
        int id;
        synchronized (pdfs) {
            id = nextPdf++;
        }
        pdfs.put(id, r);
        return obj("id", id, "sizes", sizes);
    }

    private static PdfRenderer pdf(int id) {
        PdfRenderer r = pdfs.get(id);
        if (r == null) {
            throw new IllegalStateException("no PDF " + id);
        }
        return r;
    }

    /** The page's text; PdfRenderer only reads it from Android 15 on. */
    private static String pdfText(int id, int index) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            return "";
        }
        PdfRenderer r = pdf(id);
        StringBuilder text = new StringBuilder();
        synchronized (r) {
            try (PdfRenderer.Page page = r.openPage(index)) {
                for (PdfPageTextContent part : page.getTextContents()) {
                    if (text.length() > 0) {
                        text.append('\n');
                    }
                    text.append(part.getText());
                }
            }
        }
        return text.toString();
    }

    /** Renders the page stretched to width x height on white into a PNG. */
    private static String pdfRender(int id, int index, int width, int height, String out)
            throws Exception {
        PdfRenderer r = pdf(id);
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        bitmap.eraseColor(Color.WHITE);
        synchronized (r) {
            try (PdfRenderer.Page page = r.openPage(index)) {
                page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
            }
        }
        try (OutputStream os = new FileOutputStream(out)) {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, os);
        } finally {
            bitmap.recycle();
        }
        return out;
    }

    // Audio ------------------------------------------------------------------

    private static void playAudio(String path) {
        stopAudio();
        MediaPlayer mp = new MediaPlayer();
        try {
            mp.setDataSource(path);
            mp.setOnCompletionListener(m -> {
                if (player == m) {
                    stopAudio();
                    event(obj("type", "audioDone"));
                }
            });
            mp.setOnErrorListener((m, what, extra) -> {
                Log.w(TAG, "cannot play " + path + " (" + what + "/" + extra + ")");
                if (player == m) {
                    stopAudio();
                    event(obj("type", "audioDone"));
                }
                return true;
            });
            mp.prepare();
            mp.start();
            player = mp;
        } catch (Exception e) {
            Log.w(TAG, "cannot play " + path, e);
            mp.release();
            event(obj("type", "audioDone"));
        }
    }

    private static void stopAudio() {
        if (player != null) {
            MediaPlayer mp = player;
            player = null;
            try {
                mp.stop();
            } catch (IllegalStateException ignored) {
            }
            mp.release();
        }
    }

    // Text to speech ---------------------------------------------------------

    /** The engine once it has started, or null if it could not start. */
    private static synchronized TextToSpeech ttsEngine() throws Exception {
        if (tts == null) {
            CountDownLatch ready = new CountDownLatch(1);
            int[] status = {TextToSpeech.ERROR};
            // onInit() runs on the UI thread; this waits on Qt's
            TextToSpeech engine = onUiThread(() -> new TextToSpeech(activity, s -> {
                status[0] = s;
                ready.countDown();
            }));
            if (!ready.await(10, TimeUnit.SECONDS) || status[0] != TextToSpeech.SUCCESS) {
                Log.w(TAG, "text to speech is not available");
                engine.shutdown();
                return null;
            }
            engine.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override
                public void onStart(String id) {
                }

                @Override
                public void onDone(String id) {
                    event(obj("type", "ttsDone", "id", Integer.parseInt(id)));
                }

                @Override
                public void onError(String id) {
                    onDone(id);
                }

                @Override
                public void onStop(String id, boolean interrupted) {
                    onDone(id);
                }
            });
            tts = engine;
        }
        return tts;
    }

    private static JSONArray ttsVoices() throws Exception {
        JSONArray voices = new JSONArray();
        TextToSpeech engine = ttsEngine();
        if (engine == null || engine.getVoices() == null) {
            return voices;
        }
        for (Voice v : engine.getVoices()) {
            if (!v.getFeatures().contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED)) {
                voices.put(obj("name", v.getName(), "lang", v.getLocale().toLanguageTag(),
                        "network", v.isNetworkConnectionRequired()));
            }
        }
        return voices;
    }

    /** On the UI thread; the engine was started by tts.voices (Anki asks for
     * the voices before it picks a player). */
    private static void speak(String text, String voice, double rate, int id) {
        TextToSpeech engine = tts;
        if (engine == null) {
            event(obj("type", "ttsDone", "id", id));
            return;
        }
        for (Voice v : engine.getVoices()) {
            if (v.getName().equals(voice)) {
                engine.setVoice(v);
                break;
            }
        }
        engine.setSpeechRate((float) rate);
        if (engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, String.valueOf(id)) != TextToSpeech.SUCCESS) {
            event(obj("type", "ttsDone", "id", id));
        }
    }

    // Web views --------------------------------------------------------------

    /** One android.webkit.WebView, the backend of a QWebEnginePage. */
    static class Page {
        final int id;
        final WebView view;
        /** Tells documentReady() when the main frame's DOM is parsed. */
        private static final String READY = "(function(){if(window.top!==window)return;"
                + "var f=function(){kiokuAndroid.documentReady();};"
                + "if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',f);}"
                + "else{f();}})();";
        private final List<ScriptHandler> handlers = new ArrayList<>();
        private final List<String> fallbackStart = new ArrayList<>();
        private final List<String> fallbackEnd = new ArrayList<>();
        /** Counts loads: each one starts a new document. */
        volatile int generation;
        /** Document-end scripts for the main frame, run by documentReady(). */
        private final List<String> mainEnd = new ArrayList<>();
        private final Map<Integer, JsResult> confirms = new HashMap<>();
        private int nextConfirm = 1;
        /** Whether the WebView sees the on-screen keyboard's insets. */
        volatile boolean keyboardInsets = true;
        /** URLs Python allowed in acceptNavigationRequest(), loaded once without asking again. */
        private final List<String> approved = Collections.synchronizedList(new ArrayList<>());

        Page(int id) {
            this.id = id;
            view = new WebView(activity);
            WebSettings s = view.getSettings();
            s.setJavaScriptEnabled(true);
            s.setDomStorageEnabled(true);
            s.setMediaPlaybackRequiresUserGesture(false);
            s.setAllowFileAccess(true);
            // like QtWebEngine (LocalContentCanAccessFileUrls): local pages may
            // read other local files, e.g. an add-on's pdf.js reading a PDF
            s.setAllowFileAccessFromFileURLs(true);
            s.setLoadWithOverviewMode(false);
            s.setUseWideViewPort(true);
            s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
            WebView.setWebContentsDebuggingEnabled(true);  // chrome://inspect
            view.addJavascriptInterface(new JsInterface(), "kiokuAndroid");
            view.setWebViewClient(new Client());
            view.setWebChromeClient(new Chrome());
            // Without keyboardInsets (webview.keyboardInsets: views in windows
            // that Kioku keeps above the keyboard) the WebView doesn't see the
            // on-screen keyboard. It took the keyboard's inset itself: it
            // stopped drawing the part the keyboard was about to cover, which
            // showed black until the keyboard and the window caught up.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                view.setOnApplyWindowInsetsListener((v, insets) -> v.onApplyWindowInsets(
                        keyboardInsets ? insets : new WindowInsets.Builder(insets)
                                .setInsets(WindowInsets.Type.ime(), Insets.NONE)
                                .setVisible(WindowInsets.Type.ime(), false)
                                .build()));
            }
        }

        void setScripts(JSONArray scripts) throws JSONException {
            for (ScriptHandler h : handlers) {
                h.remove();
            }
            handlers.clear();
            fallbackStart.clear();
            fallbackEnd.clear();
            mainEnd.clear();
            boolean documentStart = WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT);
            for (int i = 0; i < scripts.length(); i++) {
                JSONObject s = scripts.getJSONObject(i);
                String source = s.getString("source");
                boolean atEnd = s.getInt("when") == 1;
                if (!documentStart) {
                    (atEnd ? fallbackEnd : fallbackStart).add(source);
                } else if (atEnd && s.optBoolean("mainOnly", true)) {
                    // evaluateJavascript() once the DOM is parsed (READY): like
                    // WKUserScript's document end it runs at the top level, so
                    // declarations stay global (Anki's bridge script declares
                    // pycmd with var), and the page's CSP does not apply (the
                    // editor's forbids inline scripts and eval)
                    mainEnd.add(source);
                } else {
                    if (atEnd) {
                        source = "(function(){var f=function(){" + source + "\n};"
                                + "if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',f);}"
                                + "else{f();}})();";
                    }
                    handlers.add(WebViewCompat.addDocumentStartJavaScript(view, source,
                            Collections.singleton("*")));
                }
            }
            if (!mainEnd.isEmpty()) {
                handlers.add(WebViewCompat.addDocumentStartJavaScript(view, READY,
                        Collections.singleton("*")));
            }
        }

        private void documentReady() {
            for (String s : mainEnd) {
                view.evaluateJavascript(s, null);
            }
        }

        void load(String url, Map<String, String> headers) {
            generation++;
            approved.add(url);
            view.loadUrl(url, headers);
        }

        void answerConfirm(int token, boolean ok) {
            JsResult r = confirms.remove(token);
            if (r != null) {
                if (ok) {
                    r.confirm();
                } else {
                    r.cancel();
                }
            }
        }

        private static boolean isLocal(Uri uri) {
            String scheme = uri.getScheme();
            return "about".equals(scheme) || "data".equals(scheme) || "blob".equals(scheme)
                    || "127.0.0.1".equals(uri.getHost());
        }

        class JsInterface {
            @JavascriptInterface
            public void send(String name, String text) {
                event(obj("type", "message", "id", id, "name", name, "text", text));
            }

            @JavascriptInterface
            public void documentReady() {
                ui.post(Page.this::documentReady);
            }

            /** Read by the bridge script when a document starts (see call()). */
            @JavascriptInterface
            public int generation() {
                return generation;
            }

            @JavascriptInterface
            public void call(int callId, String text, int gen) {
                // calls still arriving from the previous document (e.g. its
                // "domDone") must not count for the one now loading
                event(obj("type", "channel", "id", id, "call", callId, "text", text,
                        "stale", gen != generation));
            }
        }

        class Client extends WebViewClient {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (approved.remove(url) || isLocal(request.getUrl())) {
                    return false;
                }
                // ask Python (acceptNavigationRequest) asynchronously; it loads
                // the URL itself if it allows it
                event(obj("type", "navigate", "id", id, "url", url,
                        "main", request.isForMainFrame(), "redirect", request.isRedirect()));
                return true;
            }

            @Override
            public void onPageStarted(WebView v, String url, Bitmap favicon) {
                for (String s : fallbackStart) {
                    v.evaluateJavascript(s, null);
                }
                event(obj("type", "loadStarted", "id", id));
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                for (String s : fallbackEnd) {
                    v.evaluateJavascript(s, null);
                }
                event(obj("type", "loadFinished", "id", id, "ok", true));
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    Log.w(TAG, "loading " + request.getUrl() + " failed: " + error.getDescription());
                    event(obj("type", "loadFinished", "id", id, "ok", false));
                }
            }
        }

        class Chrome extends WebChromeClient {
            @Override
            public boolean onConsoleMessage(ConsoleMessage message) {
                return true;  // the page prelude forwards console output itself
            }

            @Override
            public boolean onJsAlert(WebView v, String url, String message, JsResult result) {
                result.confirm();
                event(obj("type", "alert", "id", id, "text", message));
                return true;
            }

            @Override
            public boolean onJsConfirm(WebView v, String url, String message, JsResult result) {
                int token = nextConfirm++;
                confirms.put(token, result);
                event(obj("type", "confirm", "id", id, "token", token, "text", message));
                return true;
            }
        }
    }
}
