package com.kojaafrica.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.google.firebase.messaging.FirebaseMessaging;

public class MainActivity extends AppCompatActivity {
    private static final int PERMS = 100;
    private static final String BASE_URL = "https://koja-africa.onrender.com/";
    private WebView web;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestPermissionsIfNeeded();
        web = new WebView(this);
        setContentView(web);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true); s.setDomStorageEnabled(true); s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false); s.setAllowContentAccess(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);
        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onPermissionRequest(final PermissionRequest r) {
                runOnUiThread(() -> {
                    String[] wanted = new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE, PermissionRequest.RESOURCE_VIDEO_CAPTURE};
                    r.grant(wanted);
                });
            }
        });
        web.loadUrl(BASE_URL);
        FirebaseMessaging.getInstance().getToken().addOnSuccessListener(token -> registerTokenInWebView(token));
    }

    private void registerTokenInWebView(String token) {
        if (web == null) return;
        String js = "fetch('/api/connect/push-token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:" + quote(token) + ",platform:'android',device_name:'KOJA Android'})}).catch(()=>{});";
        web.post(() -> web.evaluateJavascript("javascript:(function(){" + js + "})()", null));
    }
    private String quote(String v) { return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"; }

    private void requestPermissionsIfNeeded() {
        java.util.ArrayList<String> p = new java.util.ArrayList<>();
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) p.add(Manifest.permission.POST_NOTIFICATIONS);
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) p.add(Manifest.permission.CAMERA);
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) p.add(Manifest.permission.RECORD_AUDIO);
        if (!p.isEmpty()) ActivityCompat.requestPermissions(this, p.toArray(new String[0]), PERMS);
    }
    @Override public void onBackPressed() { if (web != null && web.canGoBack()) web.goBack(); else super.onBackPressed(); }
}
