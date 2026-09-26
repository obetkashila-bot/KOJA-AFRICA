KOJA AFRICA — MEDIA MARKET READY V7 PLAYBACK + 5GB FIX

This package preserves the existing KOJA AFRICA application and KOJA Media Netflix-style structure.

FIXES IN THIS BUILD
1. Supabase per-file media limit is enforced at 5,000 MB (5 GB).
2. Studio displays the real 5,000 MB limit instead of 50 GB.
3. Server rejects anything above 5,000 MB before a Storage upload token is issued.
4. Large movies use direct resumable TUS upload to Supabase Storage; movie bytes do not pass through Render.
5. Media player receives a direct signed Storage URL for the original movie.
6. HLS is optional enhancement: if HLS fails, the player destroys HLS and explicitly loads the original video.
7. Playback fallback calls load()/play() so a fatal HLS error cannot leave a blank player.
8. Video element uses preload=auto and crossorigin=anonymous for reliable browser playback.
9. A Render Background Worker Dockerfile is included with ffmpeg + ffprobe installed.
10. Existing intro audio and Media Studio are preserved.

WEB SERVICE
Start command:
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120

ENVIRONMENT
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...   (or SUPABASE_SECRET_KEY / SUPABASE_KEY)
SUPABASE_STORAGE_BUCKET=koja-files
KOJA_HLS_BUCKET=koja-media-hls
KOJA_MEDIA_PROCESSING_ENABLED=true

Optional:
KOJA_MEDIA_DIRECT_MAX_MB=5000

SUPABASE SQL
Run KOJA_MEDIA_PROCESSING_V5.sql in Supabase SQL Editor before enabling HLS processing.

BACKGROUND WORKER
Use a separate Render Background Worker. Preferred runtime: Docker.
Dockerfile: Dockerfile.worker
It installs ffmpeg/ffprobe and runs:
python media_worker.py

The worker is not the web service. Do not replace gunicorn with the worker command on the web service.

PLAYBACK PIPELINE
Browser -> Supabase Storage direct upload -> database record -> original signed playback immediately
                                      -> processing queue -> FFmpeg -> HLS -> HLS bucket -> adaptive playback

The player does not require HLS processing to begin standard playback.
