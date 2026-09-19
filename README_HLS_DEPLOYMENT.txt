KOJA AFRICA — MEDIA V6 HLS ADAPTIVE STREAMING

FILES
- app.py: full KOJA Flask application with HLS-aware Media player/routes.
- media_worker.py: separate FFmpeg worker. Run as a Render Background Worker or another worker host.
- KOJA_MEDIA_HLS_MIGRATION.sql: additive Supabase migration.

1. SUPABASE
Run KOJA_MEDIA_HLS_MIGRATION.sql once in the Supabase SQL Editor.

Required columns are added to koja_public_posts. Existing rows remain intact.

2. WEB SERVICE
Keep the existing KOJA-AFRICA Render Web Service and its current gunicorn app:app command.
Replace its app.py with this app.py. Do not replace the service.

3. WORKER
Create a SEPARATE Render Background Worker using the same repository/code package. Start command:
  python media_worker.py

Worker environment variables:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  STORAGE_BUCKET=koja-files
  KOJA_MEDIA_WORKER_POLL_SECONDS=10

The worker requires ffmpeg and ffprobe installed on its host. On Render, use a Docker-based worker image that installs ffmpeg, or another worker host with FFmpeg available.

4. FLOW
Upload original -> row remains normal -> worker sees pending video -> FFmpeg creates only renditions that fit the source height -> HLS master + 4-second segments are uploaded to media-hls/<post_id>/ -> player uses adaptive HLS.

Typical renditions:
480p source: 360p + 480p
720p source: 360p + 480p + 720p
1080p source: 360p + 480p + 720p + 1080p

5. PLAYER
/media/watch/<id> supports:
- HLS.js where required, native HLS where available
- adaptive bitrate
- low initial rendition
- short HLS segments
- resume position
- +/-10 seconds
- fullscreen and landscape request where supported
- watch analytics
- related media

6. IMPORTANT UPLOAD LIMIT
The existing Flask MAX_CONTENT_LENGTH remains 15 MB. This package intentionally does not silently change it. For long movies/series, move future uploads to direct-to-Supabase resumable uploads or another video-ingest service instead of increasing the web request limit blindly.

7. CDN
The Flask HLS asset route is suitable for the first deployment, but high-scale KOJA Media should eventually put a CDN/cache or dedicated video delivery layer in front of HLS assets. This package does not claim Supabase Storage alone is a Netflix-scale CDN.
