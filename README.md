# KOJA AFRICA — Calling V2 Final Build

This package contains the latest KOJA Flask application upgraded for direct voice/video calling and Android background incoming-call notifications.

## Included
- app.py — upgraded KOJA Flask app
- KOJA_CALLING_V2.sql — required Supabase tables/columns/indexes
- requirements.txt — includes google-auth for Firebase Cloud Messaging HTTP v1
- render.yaml — Render deployment configuration
- .env.example — required environment variables
- android/ — Android wrapper with Firebase Cloud Messaging and incoming-call UI

## Important
The Android project needs the Firebase file generated for YOUR Firebase project:
`android/app/google-services.json`

The server needs Firebase service-account credentials through `FIREBASE_SERVICE_ACCOUNT_JSON` (recommended on Render) or `FIREBASE_SERVICE_ACCOUNT_PATH`.

The Flask app will still work for browser-to-browser calls without Firebase push. Firebase is what lets the Android client receive the incoming call when KOJA is not the foreground app.

## Supabase
Run `KOJA_CALLING_V2.sql` in the same Supabase project used by Render. It uses CREATE TABLE IF NOT EXISTS and ALTER TABLE ADD COLUMN IF NOT EXISTS; it does not require deleting existing tables.

## Render
Set:
- SUPABASE_URL
- SUPABASE_SERVICE_KEY
- SUPABASE_BUCKET
- SECRET_KEY
- SITE_URL
- FIREBASE_PROJECT_ID
- FIREBASE_SERVICE_ACCOUNT_JSON

Use `gunicorn app:app` as the start command.

## Firebase Android
1. Create/select a Firebase project.
2. Add Android app package: `com.kojaafrica.app`.
3. Download `google-services.json`.
4. Put it at `android/app/google-services.json`.
5. Build the Android project with Android Studio/Gradle.
6. Install KOJA and grant notifications, microphone and camera permissions.
7. On Android 14+, allow full-screen notifications for KOJA when Android presents the setting, because full-screen intents are restricted to eligible calling/alarm apps.

## Calling flow
Caller creates a call without requiring a contact relationship. KOJA creates the direct conversation and call record, stores an in-app notification, then sends an FCM high-priority data message to the callee's registered Android devices. The Android client displays an incoming-call UI. Answer opens `/connect/answer/<call_id>` and the existing WebRTC page completes the call.

## Limitations that are controlled by Android/network
Android and device manufacturers can restrict background activity, battery optimization, notification permissions, and full-screen intents. A user can also force-stop an app, in which case background delivery may not work until the app is opened again. WebRTC can require TURN on some NAT/mobile networks; the current build includes Google STUN and the architecture can be extended with TURN by changing the RTCPeerConnection ICE server list.
