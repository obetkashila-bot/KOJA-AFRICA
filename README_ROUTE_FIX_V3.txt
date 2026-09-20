KOJA AFRICA — Route Fix V3 — 2026-09-20

Fixes the Render BuildError for endpoint media_studio and restores route registrations for Media Studio, KOJA LIVE, and the Global Business B2B compatibility endpoint.

Routes restored:
- /studio -> media_studio
- /media-live and /media/live -> media_live
- /media-live/add and /media/live/add -> media_live_add
- /media-live/<stream_id> and /media/live/<stream_id> -> media_live_watch
- /business/<business_id>/b2b -> b2bv4_business

This is a route-registration repair. No destructive SQL is required. Preserve existing Render environment variables and gunicorn app:app.
