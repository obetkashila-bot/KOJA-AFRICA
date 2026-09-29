KOJA GLOBAL NEWS — END-TO-END CAMERA LIVE

This package preserves the existing KOJA AFRICA application and adds a real browser-camera ingest path for KOJA GLOBAL NEWS.

FLOW
Phone/PC camera -> browser MediaRecorder -> KOJA Flask ingest -> FFmpeg -> H.264/AAC HLS -> public KOJA GLOBAL NEWS player.

REQUIREMENTS
1. Run KOJA_GLOBAL_NEWS_END_TO_END.sql in Supabase.
2. Deploy app.py and requirements.txt.
3. FFmpeg is supplied through imageio-ffmpeg if the host does not already provide FFmpeg.
4. For the built-in camera encoder, use one Gunicorn worker on the Render service because the active encoder is held in process memory:
   gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120
5. External HLS .m3u8 sources remain supported.

PUBLIC CAMERA
Open Admin -> KOJA GLOBAL NEWS Live Studio, start the camera, then use GO PUBLIC WITH CAMERA. The resulting HLS URL is saved as the live broadcast source and can be viewed from /news/live.

IMPORTANT
Render instance-local storage is ephemeral. This built-in encoder is intended for active live sessions, not permanent broadcast archiving. For long-duration 24/7 channels, use a dedicated persistent encoder/media server and paste its public HLS URL into the existing HLS source field.

No Cloudflare and no KOJA NODE are required for this feature.
