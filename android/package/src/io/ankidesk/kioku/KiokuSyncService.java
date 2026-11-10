package io.ankidesk.kioku;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

/**
 * Keeps Kioku's process alive while its sync server (a thread of the Python
 * side, shared/python/kioku/syncserver.py) runs, so other apps and devices
 * can sync while Kioku is in the background. The service itself does
 * nothing but show the notification; its Stop action asks Python to stop the
 * server.
 */
public class KiokuSyncService extends Service {
    private static final String TAG = "Kioku";
    private static final String CHANNEL = "syncserver";
    private static final int NOTIFICATION = 0x6b73;
    private static final String STOP = "io.ankidesk.kioku.STOP_SYNC_SERVER";

    // A service started with startForegroundService() must call
    // startForeground() even when it is stopped right away: stopping it
    // before onStartCommand ran crashes the app
    // (ForegroundServiceDidNotStartInTimeException; the server switched on
    // and off quickly). Until then a stop is only remembered.
    private static boolean starting;
    private static boolean stopWhenStarted;

    /** From KiokuBridge: show (running) or remove the service. */
    static synchronized void update(Context context, boolean running, String text) {
        Intent intent = new Intent(context, KiokuSyncService.class);
        if (running) {
            intent.putExtra("text", text);
            try {
                context.startForegroundService(intent);
                starting = true;
                stopWhenStarted = false;
            } catch (RuntimeException e) {
                // Android 12+ refuses while the app is in the background; the
                // server still runs, but only as long as the process does
                Log.w(TAG, "cannot start the sync server's service", e);
            }
        } else if (starting) {
            stopWhenStarted = true;
        } else {
            context.stopService(intent);
        }
    }

    /** Called once startForeground() ran: whether to stop again at once. */
    private static synchronized boolean started() {
        starting = false;
        boolean stop = stopWhenStarted;
        stopWhenStarted = false;
        return stop;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && STOP.equals(intent.getAction())) {
            KiokuBridge.syncServerStopRequested();
            return START_NOT_STICKY;
        }
        String text = intent != null ? intent.getStringExtra("text") : null;
        Notification notification = notification(text != null ? text : "");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(NOTIFICATION, notification);
        }
        if (started()) {
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
        }
        // after the process dies the server is gone too: don't restart empty
        return START_NOT_STICKY;
    }

    private Notification notification(String text) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager.getNotificationChannel(CHANNEL) == null) {
            NotificationChannel channel = new NotificationChannel(CHANNEL, "Sync server",
                    NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Shown while the sync server on this phone runs");
            manager.createNotificationChannel(channel);
        }
        int immutable = PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT;
        PendingIntent open = PendingIntent.getActivity(this, 0,
                new Intent(this, KiokuActivity.class)
                        .setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_NEW_TASK),
                immutable);
        PendingIntent stop = PendingIntent.getService(this, 1,
                new Intent(this, KiokuSyncService.class).setAction(STOP), immutable);
        return new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_notify_sync_noanim)
                .setContentTitle("Sync server running")
                .setContentText(text)
                .setContentIntent(open)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(null, "Stop", stop).build())
                .build();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
