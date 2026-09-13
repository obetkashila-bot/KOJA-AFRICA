KOJA AFRICA — ALL-PLATFORM V1

This package prepares the latest KOJA production application for one shared web/PWA experience plus mobile and desktop wrappers.

BACKEND
Production backend: https://koja-africa.onrender.com
Architecture: Flask + Supabase + Render

INCLUDED
production/
  Latest production app.py, requirements, Procfile, master SQL, PWA icons and service-worker support.
web/
  PWA manifest and service-worker reference files.
mobile/
  Capacitor Android/iOS foundation using the same production URL.
desktop/
  Electron Windows/macOS/Linux foundation.
deep-links/
  Android App Links and Apple Universal Links templates.
store/
  Store-release checklist.

PWA LAYER
- /manifest.json is served by the production Flask app.
- /service-worker.js is registered by the main KOJA page.
- Install prompt handling is included for browsers that expose beforeinstallprompt.
- Offline shell fallback is included.
- KOJA icons are included in production/static/icons/.

MOBILE
Capacitor is configured for app ID com.kojaafrica.app and loads the same KOJA backend. Camera, geolocation, push-notification, filesystem and browser plugin dependencies are included as the native capability foundation.

DESKTOP
Electron targets Windows NSIS, macOS DMG and Linux AppImage. The desktop wrapper loads the same KOJA production backend and allows geolocation/media permissions.

DEEP LINKS
Replace the Android certificate fingerprint and Apple Team ID placeholders with the real release values before store release. Do not put signing secrets in this package.

IMPORTANT
This is a build-ready foundation, not a signed store release. Store signing, provisioning, notarization, certificates, keystores, APNs/FCM credentials and store accounts remain publisher-controlled.

PRESERVATION
Existing KOJA production modules remain in the production app. Document AI is preserved. The published UI remains emoji-free. Communications/WebRTC logic is not intentionally modified by this packaging layer.
