# KOJA AFRICA V6 — Flutterwave OAuth + Verified 10/90 Seller Accounting

This package upgrades the downloaded KOJA AFRICA V6 Market payment layer to Flutterwave OAuth 2.0.

## Payment flow
1. Buyer creates a KOJA Market order.
2. KOJA requests a Flutterwave OAuth 2.0 access token using `FLW_CLIENT_ID` and `FLW_CLIENT_SECRET`.
3. KOJA creates the Flutterwave hosted checkout.
4. Flutterwave redirects the buyer back to KOJA.
5. KOJA verifies the transaction server-side using the OAuth access token.
6. KOJA also accepts the signed `/webhook/flutterwave` webhook and independently verifies the transaction before settlement.
7. The order is finalized idempotently.
8. KOJA records 10% commission.
9. Seller earnings are recorded as 90% of the gross order amount (subject to any explicitly stored platform fee in the order).
10. Physical stock is reduced only after verified payment.

## Render variables
See `FLUTTERWAVE_RENDER_ENV.txt`.

Required:
- `FLW_CLIENT_ID`
- `FLW_CLIENT_SECRET`
- `FLW_SECRET_HASH`
- `FLW_ENVIRONMENT=production`
- `KOJA_MARKET_COMMISSION_RATE=0.10`
- `PAYMENT_CURRENCY=ZMW`

## Webhook
Set the Flutterwave webhook endpoint to:
`https://koja-africa.onrender.com/webhook/flutterwave`

The webhook signature is checked with HMAC-SHA256 using `FLW_SECRET_HASH`. The transaction is then verified through Flutterwave before any order is marked paid or seller earnings are recorded.

## Deployment
Use the included Procfile/render.yaml. The package has been checked with Python compilation before release.
