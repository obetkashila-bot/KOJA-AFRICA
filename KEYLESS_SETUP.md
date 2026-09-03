# KOJA Calling V2 — Keyless FCM Setup

This version removes the Firebase service-account private key from the Render server.

Architecture:
Android KOJA app -> FCM -> incoming-call screen
KOJA Flask on Render -> HTTPS + KOJA_RELAY_SECRET -> Firebase Cloud Function -> FCM

The Firebase Cloud Function uses its Google Cloud service identity/ADC. No service-account
private-key JSON is stored in Render.

## 1. Firebase Android file

Download `google-services.json` from Firebase Project settings and put it at:

`android/app/google-services.json`

The Android package name in this project is:

`com.kojaafrica.app`

## 2. Deploy the keyless relay

Install/login to Firebase CLI, then from this package directory run:

`firebase login`

Copy `.firebaserc.example` to `.firebaserc` and replace the project ID with your Firebase project ID.

Install function dependencies:

`cd functions && npm install && cd ..`

Create the relay secret in Firebase Secret Manager:

`firebase functions:secrets:set KOJA_RELAY_SECRET`

Enter a long random secret when prompted. Do NOT use your Firebase private key.

Deploy only the relay:

`firebase deploy --only functions:sendKojaPush`

Firebase will display the HTTPS URL for `sendKojaPush`.

## 3. Render variables

Keep your existing KOJA variables and add:

`FCM_RELAY_URL=https://YOUR_REGION-YOUR_PROJECT.cloudfunctions.net/sendKojaPush`

`FCM_RELAY_SECRET=THE_SAME_SECRET_USED_ABOVE`

Do NOT add:

`FIREBASE_SERVICE_ACCOUNT_JSON`
`FIREBASE_SERVICE_ACCOUNT_PATH`

Redeploy KOJA on Render.

## 4. What happens on a call

1. Caller selects voice/video call.
2. Render creates the call record in Supabase.
3. Render sends the recipient's FCM token(s) to the relay over HTTPS.
4. The relay authenticates the request with the secret.
5. Firebase Admin SDK uses the function's attached Google identity to send FCM.
6. Android receives the high-priority call data message.
7. KOJA's native incoming-call screen appears according to Android notification/full-screen rules.

## Important

This is keyless with respect to the Google service-account private key. The Render app still uses
`FCM_RELAY_SECRET` to authenticate to the relay. Keep that secret private.

A Firebase/Google Cloud service identity still exists behind the Cloud Function; the private key is
managed by Google rather than downloaded into the KOJA project.
