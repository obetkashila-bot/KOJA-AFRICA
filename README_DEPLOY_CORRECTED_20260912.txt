KOJA AFRICA — Corrected Production Push Test Patch — 2026-09-12

This package is based on the latest app(20260912-052005).py and adds only the notification test/VAPID compatibility fix.

Deploy:
1. Replace the production app.py with this app.py.
2. Keep build command: pip install -r requirements.txt
3. Keep start command: gunicorn app:app
4. Run KOJA_PRODUCTION_PATCH_20260912.sql in Supabase if it has not already been run.

Render environment variables for Web Push:
KOJA_PUSH_VAPID_PUBLIC_KEY
KOJA_PUSH_VAPID_PRIVATE_KEY
KOJA_PUSH_VAPID_SUBJECT

The test endpoint is POST /api/notifications/test and requires a logged-in user. It sends only to that user's stored push subscriptions.

Communications is not modified.
