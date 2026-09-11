KOJA AFRICA - REMAINING PRODUCTION ENGINES V1

Included:
- KOJA Live V2 (LiveKit SFU token/session layer)
- Business Staff & Permissions
- Seller payout reconciliation
- Delivery OTP/security foundation
- Business Verification V2 with licence/tax expiry fields
- Public Business Directory
- Market Growth Engine promotions
- Audit log + idempotency foundation
- Production Health checks
- Existing Accounting V2 + Business Intelligence retained

DEPLOY:
1. Run KOJA_REMAINING_PRODUCTION_V1.sql in Supabase SQL Editor.
2. Replace the current Render app.py with this app.py.
3. Keep start command: gunicorn app:app
4. Keep existing KOJA environment variables.
5. For true in-platform LiveKit video, add:
   LIVEKIT_URL
   LIVEKIT_API_KEY
   LIVEKIT_API_SECRET

COMMUNICATIONS IS NOT MODIFIED BY THIS BUILD.
