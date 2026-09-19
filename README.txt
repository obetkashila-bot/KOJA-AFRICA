KOJA Media URL Resolution Fix — 2026-09-19

Purpose:
- Fixes /media/watch/public-feed/... 404s caused by treating Supabase Storage paths as Flask watch-route IDs.
- Resolves both /media/watch/<post_id> and legacy /media/watch/<storage-path> references.
- Playback source is always /public/media/<post_id> for published media.
- Preserves the existing KOJA Media/Studio application and modules.

Deploy:
1. Replace the production app.py with this app.py.
2. Keep the existing requirements.txt and Render start command: gunicorn app:app.
3. No SQL migration is required for this URL-resolution fix.
