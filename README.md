# KOJA AFRICA — Standalone Native Android Shell

This package creates a real Android application for KOJA AFRICA. It is **not a Chrome/PWA install**.

## What this app does
- Package: `com.kojaafrica.app`
- App name: `KOJA AFRICA`
- Native Android launcher icon using the full KOJA AFRICA branding asset.
- Opens the existing production KOJA application directly in an Android WebView.
- Production backend remains: `https://koja-africa.onrender.com/`
- Supports JavaScript, cookies/session storage, file uploads, camera/microphone permission requests, and browser geolocation for existing KOJA features.
- Provides a native offline screen when the production server cannot be reached.
- Keeps the existing KOJA server services untouched.

## Important architecture boundary
The APK is independent of Chrome as an application. Android launches `com.kojaafrica.app` directly. The KOJA server and Supabase remain the backend. The APK does not duplicate or replace the Flask/Supabase services.

## Build from GitHub
1. Upload this project to the `KOJA-AFRICA` repository as the Android project (preferably in a separate branch first).
2. GitHub Actions will run `.github/workflows/build-apk.yml`.
3. Open **Actions → Build KOJA AFRICA Native APK → successful run → Artifacts**.
4. Download `KOJA-AFRICA-Standalone-APK` and extract the APK.
5. Install the APK on Android.

The workflow uses Gradle 8.7 and Android Gradle Plugin 8.6.1. The APK is signed with the standard debug signing configuration for direct testing/installation. It is not a Play Store production signing key.

## Production protection
Do not change the existing Flask routes, Supabase schema, Communications, AI, Marketplace, Payments, Delivery, Research, Assignments, Questions, Professional Services, Public/Media, or other KOJA services as part of this native shell build.
