KOJA AFRICA — PRODUCTION PATCH 2026-09-12

MASTER APP
app.py = latest app(20260912-052005).py, with additive production fixes.

FIXES IN THIS PACKAGE
1. Business Store order table migration included.
2. event_type/media/service event columns are additive and safe.
3. Push VAPID environment names support the KOJA-prefixed names:
   KOJA_PUSH_VAPID_PUBLIC_KEY
   KOJA_PUSH_VAPID_PRIVATE_KEY
   KOJA_PUSH_VAPID_SUBJECT
   Legacy VAPID_* names remain supported.
4. pywebpush remains required.
5. LiveKit server SDK dependency added: livekit-api>=1.2.1,<2.
6. Existing Communications module is not intentionally changed.

SUPABASE
Run KOJA_PRODUCTION_PATCH_20260912.sql before or with deployment.

RENDER ENVIRONMENT FOR PUSH
KOJA_PUSH_VAPID_PUBLIC_KEY = your VAPID public key
KOJA_PUSH_VAPID_PRIVATE_KEY = your VAPID private key
KOJA_PUSH_VAPID_SUBJECT = mailto:your-email@example.com

Do not put these secrets in GitHub or this README.

RENDER START
Build command: pip install -r requirements.txt
Start command: gunicorn app:app
