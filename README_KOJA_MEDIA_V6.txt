KOJA MEDIA V6 — HLS ADAPTIVE STREAMING

Package contents
- app.py: full KOJA Flask app with V6 player/progress/HLS support.
- media_worker.py: separate FFmpeg HLS processor.
- Dockerfile.media-worker: Render/background-worker image with FFmpeg.
- KOJA_MEDIA_V6_HLS_MIGRATION.sql: additive-only database migration.
- requirements-worker.txt: worker dependency.

1) Supabase
Run KOJA_MEDIA_V6_HLS_MIGRATION.sql in Supabase SQL Editor.
The migration does not drop or recreate existing tables.

2) HLS storage
The worker creates a public bucket named `koja-media-hls` automatically using the service key.
Recommended Render environment variables for both web and worker:
SUPABASE_URL
SUPABASE_SERVICE_KEY
SUPABASE_STORAGE_BUCKET (keep your existing value, normally koja-files)
KOJA_HLS_BUCKET=koja-media-hls
KOJA_HLS_PUBLIC_BASE=https://YOUR_PROJECT.supabase.co/storage/v1/object/public/koja-media-hls

For a real CDN later, set KOJA_HLS_CDN_BASE to the CDN origin/base instead. The player then uses the CDN URL without changing the Flask routes.

3) Render worker
Create a separate Background Worker service; do NOT replace the existing KOJA-AFRICA web service.
Use this Dockerfile: Dockerfile.media-worker
The worker scans published video posts, downloads the original from Supabase Storage, creates HLS renditions, uploads segments, then marks the post Ready.

4) Rendition rules
480p source -> 360p + 480p
720p source -> 360p + 480p + 720p
1080p source -> 360p + 480p + 720p + 1080p
HLS segments default to 4 seconds.

5) Player features
- HLS.js/native HLS
- Auto adaptive quality
- manual quality selector when variants exist
- resume position across devices for logged-in users
- local resume fallback
- true Continue Watching row
- persistent watch progress
- next related video after completion
- ±10 seconds
- fullscreen + landscape request where supported
- mobile horizontal swipe seeking and double-tap seeking
- existing KOJA event analytics preserved
- standard `/public/media/<post_id>` fallback while HLS is processing

6) Upload limit
The existing KOJA Flask upload limit remains 15 MB. It was NOT silently increased. For long movies/series, the next upload optimization should be direct-to-Supabase/resumable upload so the web request does not carry the whole source file.

7) CDN
Supabase public storage is the origin in V6. It is not the same as a dedicated global video CDN. Set KOJA_HLS_CDN_BASE later when a CDN is placed in front of the HLS bucket.
