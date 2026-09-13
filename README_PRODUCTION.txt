KOJA AFRICA — COMPLETE PRODUCTION PACKAGE
Built from the latest KOJA production app.py (2026-09-12) and KOJA_ALL_SQL_MASTER_20260912.sql.

FILES
- app.py: production Flask application
- KOJA_ALL_SQL_MASTER_20260912.sql: consolidated additive/idempotent database migration covering V7/V8 Business/POS, Marketplace/Monetisation, V12-V20 engines, and KOJA AI core/memory sections present in the source master
- requirements.txt: runtime dependencies used by app.py
- Procfile: Render start command

DEPLOYMENT
1. Keep the existing Render service KOJA-AFRICA.
2. Replace the repository app.py with this app.py.
3. Keep requirements.txt and Procfile.
4. Run the SQL file in Supabase SQL Editor before relying on newly added database modules.
5. Do not commit secrets. Configure existing Render environment variables separately.

SAFETY
- SQL is the supplied master SQL and is additive/idempotent in the source.
- Communications/WebRTC/FCM/LiveKit were not modified by this packaging step.
- Flutterwave code in app.py is preserved from the supplied production source; do not switch to LIVE until environment/webhook configuration has been verified.
