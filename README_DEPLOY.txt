KOJA AFRICA PRODUCTION PUSH TEST PATCH — 2026-09-12

Based on app(20260912-052005).py with the additive production fixes.

Added:
- KOJA-prefixed VAPID environment variable support with legacy fallback.
- /api/notifications/test (login required) to test the complete browser push delivery chain without exposing secrets.
- livekit-api requirement.
- existing additive Supabase migration retained.

Render:
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app

Required Render environment variables:
KOJA_PUSH_VAPID_PUBLIC_KEY
KOJA_PUSH_VAPID_PRIVATE_KEY
KOJA_PUSH_VAPID_SUBJECT=mailto:your-email@example.com

Do not put secret values in GitHub or this ZIP's README.

After deployment:
1. Log into KOJA on the phone/browser.
2. Open Notification Settings and enable phone/browser notifications.
3. POST /api/notifications/test while logged in. The endpoint returns JSON with configured, subscriptions and sent.
4. A successful test should display: KOJA Test Notification.
