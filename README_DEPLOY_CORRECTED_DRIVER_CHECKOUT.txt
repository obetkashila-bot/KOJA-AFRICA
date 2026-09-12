KOJA AFRICA — CORRECTED PRODUCTION DRIVER CHECKOUT

This package is built from the current production app.py and adds the missing automatic driver-request flow directly to KOJA Market checkout.

FLOW
1. Buyer adds a physical product to cart.
2. Buyer opens Secure Checkout.
3. Buyer sees: "KOJA AI — Find a nearby driver automatically". It is checked by default.
4. Buyer pays through Flutterwave.
5. After server-side payment verification, KOJA creates the delivery and automatically finds online approved drivers using the latest GPS when available.
6. KOJA notifies the best nearby drivers (up to 8) with the delivery request.
7. The first driver to accept wins. Acceptance is conditional on status=requested, so the same delivery cannot be claimed by two drivers.
8. Once accepted, it stops sending further requests.
9. Buyer does NOT need to open Delivery Tracking to start driver matching.
10. Existing one-OTP flow remains: seller confirms handover with the same OTP; buyer confirms receipt with the same OTP; payout follows the existing completion flow.

DEPLOY
1. Supabase SQL Editor: run KOJA_AI_DRIVER_AUTO_REQUEST_20260912.sql.
2. Replace the existing Render production app.py with this app.py.
3. Keep Render start command: gunicorn app:app
4. Deploy the existing KOJA-AFRICA Production service.
5. Open KOJA Market and checkout a physical item. The automatic driver checkbox must be visible.

IMPORTANT
- Do not make a second real payment merely to test the UI if an existing paid physical order can be used for downstream testing.
- This package does not redesign Communications.
- Existing AI, payment, delivery, notifications, one-OTP and other KOJA services are preserved.
- The driver search uses GPS when the delivery/product provides pickup coordinates; otherwise it falls back to the delivery pickup location and ranks available online drivers using available location data.
