KOJA DELIVERY OTP VERIFICATION HARDENING — 12 September 2026

The final six-digit delivery OTP is verified by KOJA's server. The KOJA screen reports VALID or INVALID. The code is not trusted merely because it has six digits.

FLOW
1. Customer receives the six-digit KOJA delivery OTP.
2. Driver opens KOJA > Verify Delivery OTP.
3. Driver enters exactly six digits.
4. KOJA sends the code to the server.
5. KOJA compares it with the delivery record.
6. Correct code: VALID OTP; delivery_confirmation_verified=true; delivery status becomes delivered.
7. Wrong code: INVALID; delivery remains unverified.
8. Five incorrect attempts lock OTP verification for that delivery.
9. Delivery completion/payout can proceed only after KOJA has recorded successful OTP verification (admin bypass remains available).

DEPLOY
1. Supabase SQL Editor: run KOJA_DELIVERY_OTP_VERIFICATION_20260912.sql.
2. Existing KOJA-AFRICA Render Production: replace app.py with this app.py.
3. Keep the existing start command: gunicorn app:app.
4. Deploy the existing KOJA-AFRICA Production service.
5. Test a physical Market or Business delivery.

No table recreation or destructive changes. Communications UI is untouched.
