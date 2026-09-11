KOJA AFRICA — PRODUCTION HARDENING V2

This package is an additive hardening layer over KOJA AFRICA All Remaining Production V1.
Communications is not modified by this package.

Included
- app.py: Production Hardening V2
- KOJA_PRODUCTION_HARDENING_V2.sql
- requirements.txt
- Procfile
- README_PRODUCTION_HARDENING_V2.txt

New controls
1. Lightweight rate limiting for sensitive auth/delivery endpoints.
2. Idempotency storage foundation for safe retries.
3. Public production-health JSON endpoint.
4. Admin production-hardening dashboard.
5. Admin payout status review actions (record/status control only; does NOT send money).
6. Admin delivery reassignment control.
7. 413 and 429 handling.
8. Audit events for new admin actions.

Deployment order
1. Run KOJA_PRODUCTION_HARDENING_V2.sql in Supabase SQL Editor.
2. Replace Render's app.py with this app.py.
3. Keep Start Command: gunicorn app:app
4. Keep existing environment variables.
5. Confirm LIVEKIT_URL/LIVEKIT_API_KEY/LIVEKIT_API_SECRET if Live V2 is required.
6. Confirm FLW_SECRET_KEY before real Flutterwave operations.

Important
This is hardening V2, not a claim that every payment, payout, delivery assignment, LiveKit moderation, or database policy is fully enterprise-grade. Actual money movement remains in the existing payment/disbursement integration and should be verified separately.
