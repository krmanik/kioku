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
 * Held while a sync with AnkiWeb runs (shared/python/kioku/ankiwebsync.py).
 * A few seconds after an app leaves the foreground Android cuts its network,
 * which failed the download of a collection and left a new profile empty. The
 * service itself does nothing but show the notification. Downloads of extra
 * files for add-ons (kioku/packs.py) hold it too, with their own title.
 */
public class KiokuAnkiWebService extends Service {
    private static final String TAG = "Kioku";
    private static final String CHANNEL = "ankiwebsync";
    private static final int NOTIFICATION = 0x6b77;

    private static final String EXTRA_TITLE = "title";

    /** From KiokuBridge: show (running) or remove the service; an empty title
     * means a sync. Starting it again while it runs updates the notification. */
    static void update(Context context, boolean running, String title) {
        Intent intent = new Intent(context, KiokuAnkiWebService.class);
        if (running) {
            intent.putExtra(EXTRA_TITLE, title);
            try {
                context.startForegroundService(intent);
            } catch (RuntimeException e) {
                // Android 12+ refuses while the app is in the background; the
                // sync still runs, but only until Android cuts the network
                Log.w(TAG, "cannot start the AnkiWeb sync service", e);
            }
        } else {
            context.stopService(intent);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String title = intent != null ? intent.getStringExtra(EXTRA_TITLE) : null;
        Notification notification = notification(
                title == null || title.isEmpty() ? "Syncing with AnkiWeb" : title);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        } else {
            startForeground(NOTIFICATION, notification);
        }
        // after the process dies the sync is gone too: don't restart empty
        return START_NOT_STICKY;
    }

    /** Android 15+: dataSync services get 6 hours a day, then must stop. */
    @Override
    public void onTimeout(int startId, int fgsType) {
        stopSelf();
    }

    private Notification notification(String title) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager.getNotificationChannel(CHANNEL) == null) {
            NotificationChannel channel = new NotificationChannel(CHANNEL, "AnkiWeb sync",
                    NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Shown while Kioku syncs with AnkiWeb");
            manager.createNotificationChannel(channel);
        }
        PendingIntent open = PendingIntent.getActivity(this, 0,
                new Intent(this, KiokuActivity.class)
                        .setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentTitle(title)
                .setContentIntent(open)
                .setOngoing(true)
                .build();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
