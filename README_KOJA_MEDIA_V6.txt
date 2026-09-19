KOJA MEDIA V6 — HLS ADAPTIVE STREAMING

This package keeps the existing KOJA Flask application and adds a streaming-first
Media layer. Communications, Market, AI and other KOJA services are not changed.

FILES
- app.py — full KOJA Flask application with Netflix-style Media cards and HLS-capable player.
- koja_media_worker.py — FFmpeg worker that creates 360p/480p/720p/1080p HLS renditions.
- KOJA_MEDIA_V6_HLS.sql — additive Supabase migration.

DEPLOY
1. Replace your existing app.py with the app.py in this ZIP.
2. Run KOJA_MEDIA_V6_HLS.sql in Supabase SQL Editor.
3. Create a Supabase Storage bucket named `koja-media-stream` and make it public for direct
   HLS playback. Keep your existing `koja-files` bucket unchanged.
4. Run the worker on a machine/service that has FFmpeg + ffprobe installed. Do NOT run
   long FFmpeg jobs inside a Render web request.
5. Set worker environment variables:
   SUPABASE_URL
   SUPABASE_SERVICE_KEY (or SUPABASE_SECRET_KEY)
   KOJA_MEDIA_HLS_BUCKET=koja-media-stream
   KOJA_MEDIA_SOURCE_BUCKET=koja-files
6. Process a video with:
   KOJA_MEDIA_POST_ID=<published-post-uuid> python koja_media_worker.py

PLAYER
- HLS master playlist preferred when `media_hls_url` exists.
- Native HLS is used where the browser supports it.
- hls.js is loaded for browsers that need it.
- Adaptive quality selector appears when multiple HLS variants exist.
- Resume position, progress, fullscreen, landscape lock attempt, +/-10 sec and double-tap skip remain.
- Small 4-second HLS segments and a 30-second playback buffer are used by the worker/player.

IMPORTANT
The web service should not transcode large videos synchronously. Use a worker or managed
video-processing service for production scale. A CDN/public object-storage layer should sit
in front of HLS assets as traffic grows.
