KOJA BUSINESS ORGANISATION CORE V1

Adds an organisation layer above the existing koja_businesses table without replacing existing Enterprise/B2B/business tables.

New routes:
/business/core
/business/<business_id>/core
/business/<business_id>/core/members
/business/<business_id>/core/departments
/business/<business_id>/core/workspace

New additive SQL:
KOJA_BUSINESS_ORGANISATION_CORE_V1.sql

Deploy order:
1. Apply the SQL in Supabase SQL Editor.
2. Replace production app.py with this package app.py.
3. Keep existing environment variables.
4. Verify /health, /business, /business/<id>/core.

Communications and existing KOJA services are not intentionally modified.
