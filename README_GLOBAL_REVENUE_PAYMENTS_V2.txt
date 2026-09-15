KOJA GLOBAL REVENUE + PAYMENTS V2

Base: KOJA Finance V2.

Adds:
- Unified revenue/payment transaction ledger
- Provider fee tracking
- Commission records
- Settlement records
- Seller/provider payout records
- Revenue invoices
- Flutterwave verification -> revenue transaction recording
- Revenue dashboard and APIs

Routes:
/revenue/v2
/revenue/v2/transactions
/revenue/v2/settlements
/revenue/v2/payouts
/revenue/v2/invoices
/api/revenue/v2/summary
/api/revenue/v2/verify/flutterwave

Important:
- Additive only; existing KOJA services remain intact.
- Communications is not modified.
- Existing Flutterwave checkout/webhook logic is not replaced.
- Payout screen records controlled payout records; it does not silently initiate a transfer.
- Apply KOJA_GLOBAL_REVENUE_PAYMENTS_V2.sql in Supabase SQL Editor before testing the new routes.
- Keep Flutterwave secrets server-side.
