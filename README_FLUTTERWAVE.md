# KOJA AFRICA — Flutterwave V3

This deployment uses Flutterwave V3 for Zambia mobile-money payments because the current merchant dashboard exposes V3 test credentials.

Set in Render:
- `FLW_SECRET_KEY`
- `FLW_SECRET_HASH`
- `FLW_ENVIRONMENT=sandbox`
- `KOJA_MARKET_COMMISSION_RATE=0.10`
- `PAYMENT_CURRENCY=ZMW`

The app uses the V3 Zambia mobile-money charge endpoint and V3 transaction verification. Webhooks are verified with `FLW_SECRET_HASH`.
