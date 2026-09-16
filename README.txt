KOJA REVENUE & PAYMENTS V2 -> PLATFORM FOUNDATIONS V2

This package connects the existing KOJA Revenue & Payments V2 operating layer to the shared Platform Foundations V2 without replacing existing payment workflows.

Connected flow:
Verified Flutterwave payment
  -> Revenue & Payments V2 transaction
  -> Unified Platform Transaction
  -> Platform Event
  -> KOJA Revenue Engine ledger

The bridge is:
- additive
- idempotent using deterministic foundation keys
- fail-soft: foundation bridge errors do not intentionally block an existing payment finalizer
- compatible with existing V20 revenue tables
- compatible with existing KOJA_GLOBAL_REVENUE_PAYMENTS_V2 tables
- Communications untouched

Deployment order:
1. Apply KOJA_PLATFORM_FOUNDATIONS_V2.sql if not already applied.
2. Apply KOJA_GLOBAL_REVENUE_PAYMENTS_V2.sql if not already applied.
3. Apply KOJA_REVENUE_PAYMENTS_PLATFORM_FOUNDATION_V2.sql.
4. Deploy this app.py to the existing KOJA-AFRICA Render Production service.
5. Test /health.
6. Log in and open /api/platform/revenue-payments/status.
7. Complete a sandbox Flutterwave payment.
8. Confirm the original payment/order remains present and that Revenue V2, koja_unified_transactions, koja_platform_events and koja_engine_revenue receive the corresponding records.

Important:
- Do not replace the current production app blindly. This app.py is based on app(20260915-070637).py and contains this integration patch.
- Existing Flutterwave verification, callbacks, webhooks, Market, Marketplace, monetization and Communications logic are retained.
