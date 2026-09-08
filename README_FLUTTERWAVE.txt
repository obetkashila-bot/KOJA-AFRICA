KOJA AFRICA V6 - FLUTTERWAVE V4 OAUTH TEST PACKAGE
====================================================
Version: 2026.09.08-V6-V4-OAUTH-MOBILE-MONEY

This package updates the main KOJA Market payment flow to Flutterwave's current V4 OAuth API.

RENDER ENVIRONMENT VARIABLES
----------------------------
FLW_CLIENT_ID=your_v4_sandbox_client_id
FLW_CLIENT_SECRET=your_v4_sandbox_client_secret
FLW_ENVIRONMENT=sandbox
FLW_SECRET_HASH=your_flutterwave_webhook_secret_hash
KOJA_MARKET_COMMISSION_RATE=0.10
PAYMENT_CURRENCY=ZMW

V4 SANDBOX API
--------------
Base URL: https://developersandbox-api.flutterwave.com
OAuth token URL: https://idp.flutterwave.com/realms/flutterwave/protocol/openid-connect/token

MAIN KOJA MARKET FLOW
---------------------
1. Create Flutterwave customer
2. Create mobile_money payment method (country code 260)
3. Create V4 charge
4. Customer authorizes payment on phone / redirect if returned
5. KOJA verifies the charge server-side
6. Webhook can finalize asynchronous payments
7. KOJA books 10% commission and seller earnings
8. Physical stock is reduced only after verified payment

SUPPORTED NETWORK SELECTOR IN KOJA
----------------------------------
MTN
Airtel
Zamtel

CALLBACK
--------
https://koja-africa.onrender.com/market/payment/callback

WEBHOOK
-------
https://koja-africa.onrender.com/webhook/flutterwave

IMPORTANT
---------
The legacy digital-marketplace compatibility route remains on Flutterwave V3 because it uses the old Flutterwave Standard hosted-payment endpoint. The main KOJA Market Buy Now flow is the V4 OAuth implementation.

Do not paste secrets into chat or commit them to GitHub.
