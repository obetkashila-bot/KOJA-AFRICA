# KOJA AFRICA — Calling V2 (Keyless FCM)

Version: 2026.09.04-CALLING-V2-KEYLESS

This package upgrades KOJA Calling V2 so the Render Flask server does **not** require a Firebase service-account private-key JSON file.

## Included
- KOJA Flask app with direct voice/video calls without requiring a contact relationship.
- WebRTC offer/answer and ICE exchange.
- Accept, reject, end, call history and in-app notifications.
- Android FCM token registration.
- Native Android incoming-call screen and high-priority FCM handling.
- Firebase Cloud Function FCM relay using the function's Google-managed service identity/ADC.
- HMAC-style shared secret between Render and the relay.
- Supabase Calling V2 SQL.
- Render configuration.

## Important architecture

`KOJA Render Flask -> HTTPS + FCM_RELAY_SECRET -> Firebase Cloud Function -> FCM -> Android KOJA`

Render no longer needs `FIREBASE_SERVICE_ACCOUNT_JSON` or `FIREBASE_SERVICE_ACCOUNT_PATH`.

Google documents Workload Identity Federation as a keyless way for external workloads to access Google Cloud resources, but Render's currently documented managed OIDC integrations do not list Google Cloud as a supported provider. Therefore this package uses a Firebase Cloud Function relay: the Google-managed function identity handles FCM, while Render authenticates to the relay with a separate application secret. This avoids a downloadable Google service-account private key on Render.

## Firebase setup

1. Create/register Android app package `com.kojaafrica.app`.
2. Download `google-services.json`.
3. Put it at `android/app/google-services.json`.
4. Do not upload this private project configuration together with secrets to a public repository.

## Deploy the keyless relay

Cloud Functions deployment requires the Firebase project to use the Blaze plan. Firebase documents a no-cost quota for Cloud Functions on Blaze, but billing must be linked.

From the package directory:

`firebase login`

Copy `.firebaserc.example` to `.firebaserc` and set your Firebase project ID.

Then:

`cd functions && npm install && cd ..`

Create the secret:

`firebase functions:secrets:set KOJA_RELAY_SECRET`

Enter a long random value and keep it private.

Deploy:

`firebase deploy --only functions:sendKojaPush`

Copy the function's HTTPS URL.

## Render

Set:

`FCM_RELAY_URL=<your deployed sendKojaPush HTTPS URL>`

`FCM_RELAY_SECRET=<the same secret entered into Firebase Secret Manager>`

Do not set:

`FIREBASE_SERVICE_ACCOUNT_JSON`

`FIREBASE_SERVICE_ACCOUNT_PATH`

Redeploy the KOJA service.

## Calling flow

1. User A calls User B.
2. KOJA creates a direct conversation/call record even if A and B are not connected.
3. KOJA sends B's FCM token(s) to the relay over HTTPS.
4. The relay verifies the secret.
5. Firebase Admin SDK sends the high-priority FCM data message using the function's Google-managed identity.
6. The Android app can show the native incoming-call UI according to Android notification and full-screen rules.
7. Answer opens the KOJA WebRTC answer flow.

## Limitations

- Android OS/OEM policies can restrict background delivery or full-screen notifications.
- Android 13+ notification permission must be granted.
- Android 14+ restricts full-screen intent use to eligible use cases and user settings.
- WebRTC may need TURN for reliable calls across difficult mobile NATs.
- This package does not claim to bypass Android force-stop behavior.
- A Firebase project may need Blaze billing to deploy Cloud Functions.
