KOJA AFRICA — KOJA WORLD
==========================

This package adds KOJA WORLD to the existing Flask app.

WHAT IT DOES
- Adds /world as the KOJA WORLD public-services gateway.
- Covers 54 African countries in the country directory.
- Adds country/category/search filters.
- Adds an in-KOJA launcher at /world/open/<service_id>.
- Falls back to the original provider website when the provider blocks iframe embedding.
- Adds /admin/world for administrators to add/remove/verify public services.
- Includes a Supabase migration and initial verified services.

IMPORTANT
KOJA WORLD is a directory/launcher, not a proxy or security bypass. External services keep control of their own authentication, terms, payments and security. KOJA should not collect banking passwords or bypass anti-embedding controls.

INSTALL
1. Replace the existing app.py with the supplied app.py.
2. Run KOJA_WORLD.sql in the Supabase SQL Editor.
3. Deploy to Render.
4. Log in as an admin and open /admin/world to add more verified public services.

INITIAL VERIFIED DESTINATIONS
- Zambia: HELSB
- Zambia: Zanaco
- Ghana: Ghana.GOV
- Nigeria: Nigeria e-Government Services
- South Africa: South African Government Services

The 54-country directory is included, but URLs are not invented for countries/services that have not yet been independently verified. Admin can add verified destinations progressively.
