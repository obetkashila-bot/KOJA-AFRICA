KOJA AFRICA V41 FINAL REPAIR
=============================

Priority completed:
1. Application/database compatibility migration.
2. Dedicated administrator login: /admin/login
   - username OR email + password
   - ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD are server-side Render variables.
3. Documents module: /documents
4. Doctor registration: /doctor/register
5. Teacher/tutor registration: /teacher/register
6. Public sitemap expanded.
7. google-auth added for Google Search Console integration.

IMPORTANT:
- Run KOJA_AFRICA_V41_DATABASE_REPAIR.sql in Supabase SQL Editor before deploying app.py.
- Set ADMIN_USERNAME, ADMIN_EMAIL and ADMIN_PASSWORD in Render Environment.
- Keep SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_STORAGE_BUCKET and SECRET_KEY configured.
- This build preserves the existing GPS/Research/Assignments/Communications foundation.
