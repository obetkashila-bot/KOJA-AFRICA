KOJA AFRICA — Flutterwave V3 Mobile Money Payment Package
Version: 2026.09.08-V6-V3-MOBILE-MONEY-FINAL

This package uses the Flutterwave V3 API because the merchant dashboard currently exposes V3 test credentials.

V3 Zambia mobile-money endpoint:
POST https://api.flutterwave.com/v3/charges?type=mobile_money_zambia

V3 verification endpoint:
GET https://api.flutterwave.com/v3/transactions/{transaction_id}/verify

Authentication:
Authorization: Bearer FLW_SECRET_KEY

Render environment variables:
FLW_SECRET_KEY=your_v3_test_or_live_secret_key
FLW_SECRET_HASH=your_webhook_secret_hash
FLW_ENVIRONMENT=sandbox
KOJA_MARKET_COMMISSION_RATE=0.10
PAYMENT_CURRENCY=ZMW

Zambia networks supported by this KOJA checkout:
MTN
AIRTEL
ZAMTEL

Main Market callback:
https://koja-africa.onrender.com/market/payment/callback

Digital Marketplace callback:
https://koja-africa.onrender.com/marketplace/payment/callback

Webhook:
https://koja-africa.onrender.com/webhook/flutterwave

Security:
- Secret key is server-side only.
- Payment is verified server-side before releasing value.
- Webhook signature is checked with FLW_SECRET_HASH.
- KOJA checks transaction reference, status, currency and amount.
- Main Market keeps the existing 10% KOJA commission / 90% seller accounting.
- Payment finalization is idempotent.
- Physical stock is reduced only after verified payment.

Do not place FLW_SECRET_KEY or FLW_SECRET_HASH in app.py, GitHub, frontend code, or chat.
