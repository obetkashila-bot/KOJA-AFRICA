KOJA MARKET V9 UPGRADE

Built on the existing KOJA Market implementation. This is an additive upgrade; it does not replace Communications or unrelated KOJA services.

Added:
1. Multi-product checkout hardening compatibility and order settlement metadata.
2. Seller wallet/payout compatibility (existing wallet/payout routes retained).
3. Escrow/protection metadata and buyer order-protection claims.
4. Existing Driver-connected delivery flow retained; tracking metadata expanded.
5. Ranked Market Discovery: relevance, popularity, rating, price, category and seller quality.
6. Seller Analytics: sales value, units, commission, net, ratings and products.
7. Buyer protection/dispute workflow plus admin resolution page.
8. Market notifications page using the existing KOJA notifications table.
9. KOJA Market AI: uses the configured KOJA AI provider when available, grounded only in current Market listings.
10. Africa expansion foundation: country/currency reference data and seller/product/order country fields.
11. Market events table for future conversion, ad and recommendation analytics.

Production deployment:
- Run KOJA_MARKET_V9_UPGRADE.sql in Supabase SQL Editor.
- Replace the deployed app.py with the supplied app.py.
- Keep Render start command: gunicorn app:app
- Do not change Communications.
- Existing Flutterwave verification remains server-side.

Important:
- The migration uses CREATE IF NOT EXISTS and ADD COLUMN IF NOT EXISTS; it does not drop or recreate existing Market tables.
- Currency expansion is a foundation. Live cross-currency payment settlement must be configured per payment provider/country before real-money use.
