KOJA V8 MARKET DELIVERY V2

Adds production hardening to the existing V1 Shop -> Road -> Home delivery system.

Included:
- OSRM road routing with road distance and ETA; Haversine fallback if routing is unavailable.
- Route geometry returned to the live tracking map and drawn as a road line.
- Multi-seller cart delivery-fee calculation from each seller/shop GPS when available.
- Driver rejection and nearest-driver reassignment.
- Safer acceptance check to reduce duplicate driver assignment.
- Customer/seller delivery notifications through the existing koja_notifications table.
- Driver delivery earnings ledger; delivery fee is separated from seller item revenue.
- Seller/KOJA commission is calculated from item amount, not delivery fee.
- Admin Market Delivery Control Center at /admin/market-deliveries.
- Customer-only delivery OTP display.

DEPLOY
1. Run KOJA_V8_MARKET_ALL_MIGRATIONS.sql in the existing Supabase project. It includes V1 + V2 safe/idempotent changes.
2. Replace app.py in the existing KOJA-AFRICA GitHub repository.
3. Commit the file.
4. Render -> KOJA ZM -> Production -> KOJA-AFRICA -> Manual Deploy -> Deploy latest commit.
5. Keep gunicorn app:app.

OPTIONAL ENVIRONMENT VARIABLES
KOJA_DELIVERY_BASE_FEE=15
KOJA_DELIVERY_PER_KM=3
KOJA_DELIVERY_MAX_RADIUS_KM=50
KOJA_OSRM_URL=https://router.project-osrm.org
KOJA_DELIVERY_SPEED_KMH=30

Important:
- Existing Render deployment remains the target.
- Communications/WebRTC/FCM/LiveKit was not intentionally modified.
- OSRM is an external routing service; the app falls back to straight-line ETA if routing is unavailable.
