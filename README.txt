KOJA PROFESSIONAL SERVICES MARKETPLACE V1

Based on exact KOJA production source app(20260915-070637).py plus the cumulative Services fix.

FIXED
- /services no longer calls the nonexistent market endpoint; it uses koja_market.
- /professional/book/<provider_id> render_page duplicate-title error fixed.

ADDITIVE MARKETPLACE
- Professional services catalogue with appointment/live/project/digital service models
- Customer service requests
- Quotations and quote acceptance
- Project jobs and payment records
- Flutterwave Zambia mobile-money checkout + server verification for professional payments
- Configurable commission settings
- Professional earnings and payout-status tracking
- Reviews
- Verification workflow
- Customer dashboard
- Professional dashboard
- Admin Professional Services control centre
- Natural-language professional matching foundation
- Paid live-session data model
- Connect+ remains untouched

DATABASE
Run KOJA_PROFESSIONAL_SERVICES_MARKETPLACE_V1.sql in Supabase before using the new marketplace tables. It is additive and uses CREATE TABLE IF NOT EXISTS.

DEPLOY
Replace the existing production app.py in the KOJA-AFRICA repository. Keep existing environment variables. Do not replace the Render service.

TEST
/health
/services
/professional/marketplace
/setup/professional-services-sql
