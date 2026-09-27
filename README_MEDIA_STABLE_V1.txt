KOJA AFRICA — V3 LIVE + MEDIA STABLE V1

BASELINE
This package is built from the verified KOJA AFRICA RELIABILITY V3 application.
The V3 LIVE engine is preserved as the production baseline.

MEDIA
- Direct browser -> Supabase Storage upload
- Resumable TUS upload for large files
- Maximum individual Media upload: 5 GB
- Render is not used to carry the movie bytes
- Studio publish/draft flow preserved
- Media processing/HLS fields supported where the existing worker/database are present

PLAYBACK HARDENING
- HLS playback remains preferred when an HLS master URL exists
- Fatal HLS errors destroy the HLS instance and explicitly load the original signed media URL
- Native HLS path calls load() before playback
- Browser playback is never left pointing at a failed HLS source

LIVE
- V3 reconnect/retry logic preserved
- 60-second initial load grace
- 30-second live-delay guard
- Temporary upstream failures trigger recovery
- If upstream has stopped serving the stream, KOJA cannot recreate it

RENDER WEB SERVICE
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --keep-alive 5 --max-requests 1200 --max-requests-jitter 100

REQUIRED ENVIRONMENT
SUPABASE_URL
SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_KEY / SUPABASE_KEY)
SECRET_KEY or FLASK_SECRET_KEY

OPTIONAL MEDIA
SUPABASE_STORAGE_BUCKET (default: koja-files)
KOJA_HLS_BUCKET (default: koja-media-hls)
KOJA_HLS_PUBLIC_BASE
KOJA_HLS_CDN_BASE
KOJA_MEDIA_DIRECT_MAX_GB (capped by this build at 5 GB)

IMPORTANT
The 5 GB limit is an individual upload guard. It is not the total Supabase Storage quota.
A separate Media worker is required if automatic FFmpeg transcoding/HLS generation is enabled.
Do not replace the V3 LIVE code with the failed V5 implementation.
