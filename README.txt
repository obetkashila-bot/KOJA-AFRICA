KOJA GLOBAL COMMERCE V2

Cumulative source: preserves the existing KOJA production services and prior B2B, Finance V2, Supply Chain V2, Workforce V2, Sales & CRM V2 and Enterprise V2 layers.

Global Commerce V2 adds:
- Country and currency registry
- FX rate infrastructure
- Tax profiles
- Multi-country legal/operating entities
- Cross-border trade lanes
- Cross-border orders
- Settlement records
- Compliance documents
- Global commerce audit events
- Finance V2 bridge helper for future settlement posting
- Global Commerce dashboard and summary API

Supabase:
Run KOJA_GLOBAL_COMMERCE_V2.sql first. It is additive/update-safe and contains no DROP or TRUNCATE operations.

Render:
Deploy the included app.py to the existing KOJA AFRICA production service after the SQL completes successfully.

Routes:
/global-commerce
/global-commerce/countries
/global-commerce/orders
/api/global-commerce/summary
/api/global-commerce/fx
