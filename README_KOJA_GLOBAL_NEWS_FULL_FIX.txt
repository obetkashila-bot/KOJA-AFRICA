KOJA GLOBAL NEWS FULL FIX

This upgrade preserves the existing KOJA AFRICA navigation and existing KOJA News article system.

Included:
- KOJA Global News naming and global country/region/city/language/timezone fields.
- Existing HLS .m3u8 broadcast architecture; no Cloudflare.
- Global News Live Studio.
- Main Desk, Interview, Reporter, Newsroom, Breaking, Parliament, Africa, World, Business, Sports and Weather scenes.
- Supabase Storage Studio Assets: backgrounds and desk overlays.
- Scene-specific asset selection in Live Studio.
- Selected assets are saved to the live broadcast and displayed on public /news/live.
- Admin dashboard links for Global News, Live Studio and Studio Assets.
- Existing More menu structure is preserved; News is not duplicated into a new top-level menu.
- Browser camera is local preview only; it does not pretend to publish HLS.

SUPABASE:
1. Run KOJA_GLOBAL_NEWS_FULL_FIX.sql in Supabase SQL Editor.
2. Ensure the storage bucket named by KOJA_NEWS_STUDIO_BUCKET exists. If that env var is absent, the app uses SUPABASE_STORAGE_BUCKET (normally koja-files).
3. Ensure the service key used by the app has permission to upload/delete objects in that bucket.

DEPLOY:
Replace the production app.py with the included app.py and deploy normally with gunicorn app:app.
