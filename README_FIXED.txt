KOJA AFRICA V6 FULL — Flutterwave V3 Zambia + Audio FIX2

Base: KOJA V6 FULL BUY/SELL UI FIX1 V52.
Preserved: KOJA Market, Digital Marketplace/Media, AI, Research, Communications, Drivers/Delivery and existing services.
Payment: Flutterwave V3 Zambia Mobile Money charges endpoint with MTN/Airtel/Zamtel, server-side transaction verification, ZMW, existing 10% KOJA commission / seller earnings logic retained.
Audio: remote call playback gain boost up to 1.8x in supported browsers; device master volume still applies.

Render start command:
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --graceful-timeout 30 --keep-alive 5

Keep existing Render environment variables. Required Flutterwave V3 variables:
FLW_SECRET_KEY
FLW_SECRET_HASH (if using webhook verification)
FLW_ENVIRONMENT=sandbox
PAYMENT_CURRENCY=ZMW
KOJA_MARKET_COMMISSION_RATE=0.10
