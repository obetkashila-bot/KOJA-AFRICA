KOJA B2B + PROFESSIONAL SERVICES UNIFIED V3

Base: current production app(20260915-070637).py

Adds a unified B2B front door around existing Procurement, Supply Chain, CRM, Finance, Marketplace, Payments, Delivery and Professional Services.

New routes:
/b2b
/b2b/<business_id>
/b2b/<business_id>/listings
/b2b/<business_id>/listing/new
/b2b/<business_id>/requests
/b2b/<business_id>/request/new
/b2b/request/<request_id>
/b2b/api/match

Communications / Connect+ is untouched.
SQL is additive/idempotent. Run SQL before using the new B2B pages.
