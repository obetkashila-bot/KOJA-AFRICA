KOJA AFRICA — PRODUCTION ANDROID APK BUILD PACKAGE

Source: latest KOJA production app available on 2026-09-12.
Backend: https://koja-africa.onrender.com
Android application ID: com.kojaafrica.app

IMPORTANT
This package is an Android build wrapper around the existing KOJA production web platform. The Capacitor Android app opens the existing Render Production backend. It does not replace Render, Supabase, Flutterwave, or the existing KOJA services.

The included app.py is the Render-startup-hardened production app source so committing this package does not intentionally reintroduce the Render health-check dependency problem.

BUILD
1. Upload/replace the package contents in the KOJA-AFRICA GitHub repository.
2. Commit to main or master.
3. GitHub Actions will run "KOJA AFRICA Android APK Build".
4. Open the completed workflow run.
5. Under Artifacts, download "koja-africa-production-apk".
6. Extract the artifact ZIP and install app-debug.apk on Android.

RELEASE SIGNING
For a signed release APK, add these GitHub repository secrets:
KOJA_KEYSTORE_BASE64
KOJA_KEYSTORE_PASSWORD
KOJA_KEY_ALIAS
KOJA_KEY_PASSWORD

The workflow then produces the artifact "koja-africa-production-release-apk".

Do not commit a keystore, passwords, API keys, Supabase service-role keys, Flutterwave secrets, or AI provider keys.

WHY DEBUG APK FIRST
The debug APK is the fastest installation test. Android's documentation distinguishes debug APKs for testing/sharing from signed release artifacts for distribution. Capacitor also supports building APK/AAB artifacts through its build tooling.

RENDER SAFETY
Keep the existing KOJA-AFRICA Render Production service. Do not use Render's Move function. The APK points to the existing production URL.
