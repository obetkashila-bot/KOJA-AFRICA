KOJA AFRICA V10 — $10B SCALE ARCHITECTURE FOUNDATION

Purpose
This release adds the platform foundation for multi-country commerce, universal discovery, developer APIs, advertising events, procurement quotes, affiliate events and scale administration.

Preservation
- Existing Render KOJA-AFRICA deployment remains the target.
- Existing Market/Delivery functionality is preserved.
- Existing AI provider router is preserved.
- KOJA Communications is intentionally untouched.

Supabase
Run KOJA_V10_SCALE_ARCHITECTURE.sql in Supabase SQL Editor. It is safe/idempotent and uses CREATE TABLE IF NOT EXISTS / ALTER TABLE ADD COLUMN IF NOT EXISTS.

Render
Replace app.py in the existing KOJA-AFRICA GitHub repository. Keep gunicorn app:app.

New pages
/platform
/platform/search?q=...
/platform/api-key
/admin/v10-scale
/api/v10/health
/api/v10/countries

Important
The $10B by 2030 figure is an ambitious target, not a guaranteed forecast. This release provides infrastructure; it does not claim that future revenue already exists.
