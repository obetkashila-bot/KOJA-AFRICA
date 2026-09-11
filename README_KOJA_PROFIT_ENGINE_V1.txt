KOJA AFRICA — PROFIT ENGINE V1

Purpose
- Unified platform monetization layer.
- AI credit purchases through the existing Flutterwave Zambia mobile-money flow.
- Unified KOJA revenue ledger.
- Admin profit/revenue dashboard.
- Connects new revenue to the existing V20 engine_revenue table when available.

Safe scope
- Additive SQL only.
- Existing Market, Business, Deliveries, AI, Accounting and Communications code is preserved.
- Communications is not modified.

Deploy
1. Run KOJA_PROFIT_ENGINE_V1.sql in Supabase SQL Editor.
2. Replace the current Render/GitHub app.py with app_profit_v1.py renamed to app.py.
3. Keep the existing Render start command: gunicorn app:app.
4. Keep FLW_SECRET_KEY configured. Do not switch to real money until the Flutterwave account and webhook have been tested with a small controlled transaction.
5. Open /profit after login. Admins can open /admin/profit-engine.

AI credit pricing
- Default: K10 per credit.
- Override with Render environment variable KOJA_AI_CREDIT_PRICE.
- Override the service-fee calculation with KOJA_PROFIT_FEE_RATE (default 5%).

Existing monetization
KOJA already has seller plans, boosts, featured listings, advertising, marketplace fees, seller payouts and business subscriptions. This V1 adds the unified revenue layer and paid AI credits on top of those foundations.
