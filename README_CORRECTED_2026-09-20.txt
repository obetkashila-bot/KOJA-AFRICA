KOJA AFRICA — FULL REGRESSION CORRECTION
2026-09-20

This package fixes two route regressions found in the deployed application:

1. Global Business: the Global Business hub referenced the endpoint
   `b2bv4_business`, while the B2B workspace function was registered only as
   `b2bv4_centre`. An endpoint-compatible route alias has been restored.

2. KOJA Media: the Media V6 template referenced `media_live`,
   `media_live_add`, and `media_live_watch`, but those functions had lost their
   Flask route decorators. The /media-live and /media/live routes are restored.

The package preserves the existing full Flask application and does not remove
Communications, Marketplace, AI, Business, B2B, or other KOJA services.

Deployment:
- Replace the repository app.py with this app.py.
- Keep the existing Render start command: gunicorn app:app
- Keep existing environment variables.
- No destructive SQL operation is required for these route fixes.

The included SQL remains additive/update-safe for the previously identified
Global Business dependencies, but it should only be applied if those tables
are missing from Supabase.
