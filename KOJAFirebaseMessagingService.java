package com.kojaafrica.app;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

public class KOJAFirebaseMessagingService extends FirebaseMessagingService {
    public static final String CHANNEL = "koja_calls";
    @Override public void onNewToken(String token) { getSharedPreferences("koja", MODE_PRIVATE).edit().putString("fcm_token", token).apply(); }

    @Override public void onMessageReceived(RemoteMessage msg) {
        String type = msg.getData().get("type");
        if (!"incoming_call".equals(type)) return;
        String callId = msg.getData().get("call_id");
        String caller = msg.getData().get("caller_name");
        String mode = msg.getData().get("mode");
        Intent i = new Intent(this, IncomingCallActivity.class);
        i.putExtra("call_id", callId); i.putExtra("caller_name", caller); i.putExtra("mode", mode);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, safeId(callId), i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        createChannel();
        NotificationCompat.Builder b = new NotificationCompat.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.sym_call_incoming).setContentTitle("KOJA " + title(mode))
                .setContentText((caller == null ? "KOJA user" : caller) + " is calling you")
                .setPriority(NotificationCompat.PRIORITY_MAX).setCategory(NotificationCompat.CATEGORY_CALL)
                .setOngoing(true).setAutoCancel(false).setFullScreenIntent(pi, true).setContentIntent(pi);
        ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(safeId(callId), b.build());
        try { startActivity(i); } catch (Exception ignored) {}
    }
    private String title(String m) { return "video".equals(m) ? "Video Call" : "Voice Call"; }
    private int safeId(String s) { return Math.abs((s == null ? System.currentTimeMillis()+"" : s).hashCode()); }
    private void createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel c = new NotificationChannel(CHANNEL, "KOJA Incoming Calls", NotificationManager.IMPORTANCE_HIGH);
            c.setDescription("Incoming KOJA voice and video calls"); c.setLockscreenVisibility(android.app.Notification.VISIBILITY_PUBLIC);
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(c);
        }
    }
}
