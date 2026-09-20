KOJA AFRICA MEDIA ROUTE FIX V4 — 2026-09-20

Fixes the Render BuildError:
Could not build url for endpoint 'media_watch' with values ['post_id'].

Root cause: media_watch() existed but had no Flask route decorator, while /media-next generated url_for('media_watch', post_id=...).

Restored route:
/media/watch/<post_id>
endpoint: media_watch

Preserves the V3 fixes for:
- media_studio (/studio)
- KOJA LIVE routes
- Global Business b2bv4_business endpoint alias

No Communications, Marketplace, AI, or unrelated service changes were intentionally made.

Deploy: replace app.py in the existing KOJA-AFRICA Render service. Keep gunicorn app:app and existing environment variables.
