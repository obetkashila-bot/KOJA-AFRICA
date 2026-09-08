KOJA AFRICA V6 — FLUTTERWAVE V4 OAUTH FINAL
===========================================
Version: 2026.09.08-V6-V4-OAUTH-FINAL

This package uses Flutterwave's current V4 OAuth 2.0 API for KOJA Market payments.
The legacy V3 payment endpoint is not used by KOJA Market checkout.

RENDER ENVIRONMENT VARIABLES
----------------------------
FLW_CLIENT_ID=your_v4_sandbox_client_id
FLW_CLIENT_SECRET=your_v4_sandbox_client_secret
FLW_SECRET_HASH=your_flutterwave_webhook_secret_hash
FLW_ENVIRONMENT=sandbox
KOJA_MARKET_COMMISSION_RATE=0.10
PAYMENT_CURRENCY=ZMW

For live production, change only:
FLW_CLIENT_ID=your_v4_production_client_id
FLW_CLIENT_SECRET=your_v4_production_client_secret
FLW_ENVIRONMENT=production

V4 API BASE URLS
----------------
Sandbox:    https://developersandbox-api.flutterwave.com
Production: https://f4bexperience.flutterwave.com
OAuth:      https://idp.flutterwave.com/realms/flutterwave/protocol/openid-connect/token

KOJA PAYMENT FLOW
-----------------
1. KOJA obtains a short-lived OAuth access token using Client ID + Client Secret.
2. KOJA sends a V4 Orchestrator direct-charge request.
3. For Zambia checkout, KOJA sends country code 260 and the selected mobile-money network.
4. Flutterwave returns the charge and any required redirect/payment instructions.
5. KOJA stores the charge ID against the order.
6. KOJA verifies the charge server-side before releasing value.
7. Flutterwave webhook events are HMAC-SHA256 verified.
8. KOJA finalizes the order idempotently.
9. KOJA records exactly 10% commission and 90% seller earnings for Market orders.
10. Physical stock is reduced only after verified payment.

SUPPORTED KOJA MOBILE MONEY NETWORKS
------------------------------------
MTN
Airtel
Zamtel

CALLBACK
--------
https://koja-africa.onrender.com/market/payment/callback

Digital marketplace compatibility callback:
https://koja-africa.onrender.com/marketplace/payment/callback

WEBHOOK
-------
https://koja-africa.onrender.com/webhook/flutterwave

SECURITY
--------
Never put Client Secret, Secret Hash, access tokens, or other secrets in app.py,
GitHub, frontend JavaScript, screenshots, or chat messages.

Flutterwave V4 authentication and environment documentation:
https://developer.flutterwave.com/docs/authentication
https://developer.flutterwave.com/docs/environments
