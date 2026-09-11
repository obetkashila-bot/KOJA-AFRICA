KOJA AFRICA — FULFILLMENT HARDENING V7

This package is based on the latest KOJA Unified Fulfillment V6 AI Driver Matching + GO LIVE build.

HARDENING INCLUDED
1. Business Store order table is created additively if missing: public.koja_business_orders.
2. Business Store compatibility columns and indexes are ensured.
3. Market paid-order finalization now uses a Supabase PostgreSQL transaction function:
   koja_finalize_market_order_atomic().
   It locks the order and product, prevents overselling, decrements physical stock atomically,
   unpublishes one-of-one listings when stock reaches zero, and marks the order paid in the same transaction.
4. Driver delivery availability/claim indexes are added for production-scale lookup.
5. Tracking/pickup-code indexes are added without changing existing data.
6. Existing Communications/Connect functionality is not modified.

DEPLOY
1. Run KOJA_AFRICA_FULFILLMENT_V5.sql in Supabase SQL Editor.
2. Deploy this app.py to the existing KOJA-AFRICA Render service.
3. Do not delete/recreate existing tables.
4. Keep existing Render environment variables.

IMPORTANT
The SQL is additive/idempotent. The atomic Market finalization function requires the app's Supabase service-role access,
which is already how the server-side REST layer operates.

After deployment test:
Buyer payment -> order paid -> stock decremented once -> seller notification -> delivery created -> driver claims -> pickup verification.
