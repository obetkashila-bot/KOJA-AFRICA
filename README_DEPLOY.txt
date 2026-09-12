KOJA AFRICA — ALL-IN-ONE PRODUCTION BUILD
2026-09-12 — HEALTH-HARDENED

SOURCE
This build is based on KOJA_MERGED_ALL_DUPLICATE_MODULES_20260912.
It preserves the merged user-facing module structure and existing routes.

CANONICAL MODULES
1. KOJA Connect — communication, messaging, voice/video calls, groups, media and status.
2. KOJA Market — physical + digital commerce.
3. KOJA Delivery & Drivers — delivery requests, driver operations and tracking.
4. KOJA AI — platform AI.
5. KOJA Engines — all 11 production engines.
6. Notifications — unified notification center.

HEALTH / STARTUP HARDENING
- /health is now dependency-free and non-blocking.
- /health does NOT call Supabase, Storage, Flutterwave, AI providers or driver tables.
- LiveKit SDK import is optional at process startup; a missing SDK cannot prevent Flask from starting.
- LiveKit-dependent endpoints return a controlled 503 when the SDK is unavailable.
- No database connection is opened during Flask startup.
- Python syntax was compiled successfully before packaging.

RENDER
Existing service: KOJA-AFRICA
Existing environment: Production
Build command: pip install -r requirements.txt
Start command: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --graceful-timeout 30 --keep-alive 5
Health check path: /health

DEPLOY STEPS
1. Keep the current Live deployment until the new deployment becomes Live.
2. Replace the repository app.py with this package's app.py.
3. Keep requirements.txt and Procfile from this package.
4. Commit/push to the existing KOJA-AFRICA repository.
5. Let Render Auto-Deploy, or use Manual Deploy.
6. Watch the deploy log for the service to start.
7. Confirm Render health check changes to healthy.
8. Only after the new deployment is Live, test /health and the KOJA home page.
9. Then test KOJA Engines, Notifications, KOJA Connect, KOJA Market, KOJA AI and Delivery.

IMPORTANT
- Do not press Move in Render.
- Do not delete or replace the existing Render Production service.
- Do not run destructive SQL for this build.
- Existing Supabase data is preserved; this package does not recreate tables at startup.
