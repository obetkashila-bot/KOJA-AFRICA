KOJA AFRICA V7 COMPLETE — MONETIZATION + GROWTH

Built on the verified V6/FIX11 payment foundation.
Includes: seller subscriptions, boosts, featured listings, advertising, 10% marketplace commission, seller wallet/payout requests, revenue ledger, seller verification, referrals, AI plan framework, reviews/search/filter foundations, admin commerce/growth controls, payment reconciliation, Flutterwave V3 Zambia checkout/webhook/server verification, service worker and existing Communications preserved.

DEPLOY
1. Run KOJA_V7_MONETIZATION.sql in the existing Supabase project.
2. Deploy this ZIP to the existing Render KOJA-AFRICA service.
3. Keep existing environment variables, especially FLW_SECRET_KEY, FLW_SECRET_HASH, FLW_ENVIRONMENT=sandbox, PAYMENT_CURRENCY=ZMW and KOJA_MARKET_COMMISSION_RATE=0.10.
4. Do not replace the existing Supabase database; the SQL uses CREATE TABLE IF NOT EXISTS.
5. After deployment test: /health, /market, product page, checkout, webhook, /market/my, /market/wallet, /market/seller/verification, /referrals, /ai/plan and /admin/monetization.

IMPORTANT: AI paid plans are a monetization framework in this release. Premium access should only be marked active after a verified payment; do not manually grant paid access from the browser.
