KOJA AUTOMATIC NOTIFICATIONS V1 — 2026-09-12

Included:
- Automatic KOJA notifications for new text messages.
- Automatic notifications for photos, files and voice messages.
- Incoming voice/video call notifications.
- Automatic missed-call notifications when a ringing call is ended or expires after 120 seconds.
- Group-call notifications.
- Business order confirmation for the business and buyer.
- Existing Market, Delivery, AI, connection-request and system notification flow preserved.
- KOJA-branded VAPID environment names.
- Existing push subscription schema fixed additively.
- No Communications UI redesign or unrelated service changes.

SUPABASE:
1. Open Supabase SQL Editor.
2. Run KOJA_AUTOMATIC_NOTIFICATIONS_20260912.sql.
3. Confirm the three notification tables exist and the preference table contains business_enabled and calls_enabled.

RENDER — EXISTING KOJA-AFRICA:
Replace app.py with this package's app.py.
Keep gunicorn command: gunicorn app:app
Keep existing environment variables.
Ensure these KOJA push variables exist:
KOJA_PUSH_VAPID_PUBLIC_KEY
KOJA_PUSH_VAPID_PRIVATE_KEY
KOJA_PUSH_VAPID_SUBJECT
Do not paste secrets into chat.

AFTER DEPLOY:
1. Sign in to KOJA.
2. Open /notification-settings.
3. Enable KOJA notifications.
4. Save settings.
5. Send a test notification if that button exists in the current production build.
6. Send a KOJA message to another account: recipient should receive a notification automatically.
7. Start a call and end it while ringing: recipient should receive a missed-call notification.
8. Complete a business-store payment: buyer and business receive automatic order notifications.

NOTIFICATION TYPES:
Messages, chat, photos, files, voice messages, incoming calls, missed calls, group calls, connection requests, business orders, market/orders, delivery/driver updates, KOJA AI, and system/account events.
