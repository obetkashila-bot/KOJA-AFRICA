KOJA AFRICA — E2E V4

Apply SQL in this order in Supabase:
1. KOJA_E2E_V1_MIGRATION.sql
2. KOJA_E2E_V2_MIGRATION.sql
3. KOJA_E2E_V4_MIGRATION.sql

V4 adds idempotency, a universal E2E ledger, webhook-event storage, payment reconciliation, refunds, admin control, and automatic appointment/Market-flow E2E linking.

Connect+ / Communications is not modified.

Deploy app.py with the existing Render start command: gunicorn app:app
