KOJA AFRICA — Flutterwave V3 Zambia Mobile Money FIX
Version: 2026.09.08-FLW-V3-ZM-MM-FIX1

This package fixes the marketplace payment-start failure caused by the old /v3/payments checkout call.

Flutterwave V3 endpoint used:
https://api.flutterwave.com/v3/charges?type=mobile_money_zambia

Required Render environment variables:
FLW_SECRET_KEY=<your Flutterwave V3 Test Secret Key>
FLW_SECRET_HASH=<same secret hash configured in Flutterwave Webhooks>
FLW_ENVIRONMENT=sandbox
PAYMENT_CURRENCY=ZMW

Webhook URL:
https://koja-africa.onrender.com/webhook/flutterwave

Supported networks:
MTN
AIRTEL
ZAMTEL

The app creates the KOJA marketplace order first, then starts a Zambia mobile-money charge. It redirects the customer to Flutterwave's authorization URL when returned, and verifies the final transaction server-side before marking the order paid.
