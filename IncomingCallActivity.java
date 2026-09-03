package com.kojaafrica.app;

import android.app.Activity;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class IncomingCallActivity extends Activity {
    private static final String BASE_URL = "https://koja-africa.onrender.com";
    private String callId;
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        callId = getIntent().getStringExtra("call_id");
        String caller = getIntent().getStringExtra("caller_name");
        String mode = getIntent().getStringExtra("mode");
        getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout box = new LinearLayout(this); box.setOrientation(LinearLayout.VERTICAL); box.setGravity(Gravity.CENTER); box.setPadding(36,60,36,60);
        TextView title = new TextView(this); title.setText("Incoming " + ("video".equals(mode)?"Video":"Voice") + " Call\n\n" + (caller==null?"KOJA User":caller)); title.setTextSize(26); title.setGravity(Gravity.CENTER); box.addView(title);
        Button answer = new Button(this); answer.setText("Answer"); box.addView(answer);
        Button reject = new Button(this); reject.setText("Reject"); box.addView(reject);
        setContentView(box);
        answer.setOnClickListener(v -> openAnswer());
        reject.setOnClickListener(v -> { rejectCall(); finish(); });
    }
    private void openAnswer() {
        WebView w = new WebView(this); WebSettings s=w.getSettings(); s.setJavaScriptEnabled(true); s.setDomStorageEnabled(true); s.setMediaPlaybackRequiresUserGesture(false);
        CookieManager.getInstance().setAcceptCookie(true); CookieManager.getInstance().setAcceptThirdPartyCookies(w,true);
        w.setWebChromeClient(new android.webkit.WebChromeClient(){ @Override public void onPermissionRequest(android.webkit.PermissionRequest r){runOnUiThread(()->r.grant(new String[]{android.webkit.PermissionRequest.RESOURCE_AUDIO_CAPTURE,android.webkit.PermissionRequest.RESOURCE_VIDEO_CAPTURE}));}});
        w.loadUrl(BASE_URL + "/connect/answer/" + callId); setContentView(w);
    }
    private void rejectCall() {
        try {
            URL u=new URL(BASE_URL+"/api/connect/call/reject/"+callId); HttpURLConnection c=(HttpURLConnection)u.openConnection(); c.setRequestMethod("POST"); c.setDoOutput(true); c.setRequestProperty("Content-Type","application/json");
            String cookie=CookieManager.getInstance().getCookie(BASE_URL); if(cookie!=null)c.setRequestProperty("Cookie",cookie); OutputStream o=c.getOutputStream();o.write("{}".getBytes(java.nio.charset.StandardCharsets.UTF_8));o.close();c.getResponseCode();c.disconnect();
        } catch(Exception ignored) {}
    }
}
