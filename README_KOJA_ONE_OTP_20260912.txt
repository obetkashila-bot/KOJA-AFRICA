KOJA ONE-OTP DELIVERY — 2026-09-12

PURPOSE
Replace the separate seller OTP + customer delivery OTP flow with one 6-digit KOJA order OTP.

SIMPLE FLOW
1. Buyer pays.
2. KOJA creates ONE six-digit order OTP.
3. Buyer receives the OTP. The assigned driver also receives an automatic KOJA notification that includes the OTP.
4. Driver reaches seller.
5. Seller opens KOJA Seller Confirmation and enters the SAME OTP. KOJA shows VALID and marks the handover/in-transit.
6. Driver delivers the order.
7. Buyer opens KOJA Confirm Delivery and enters the SAME OTP.
8. KOJA marks the order delivered/completed and releases/records the driver payout.

SECURITY
- Buyer confirmation is required before delivery payout is released/recorded.
- Seller handover is required before buyer delivery confirmation.
- Five wrong OTP attempts lock verification.
- The OTP is never generated separately for seller and buyer on new deliveries.
- Existing unfinished deliveries are synchronized so seller_pickup_otp matches delivery_confirmation_code.

DEPLOY
1. Supabase SQL Editor: run KOJA_ONE_OTP_DELIVERY_20260912.sql.
2. Replace the production app.py with the included app.py.
3. Keep Render command: gunicorn app:app.
4. Deploy the existing KOJA-AFRICA Production service.
5. Test with a controlled low-value/test order before any valuable transaction.

IMPORTANT
Do not make another payment just to test the code. Use the existing paid delivery if it is still active.
Communications UI is not redesigned by this patch.
