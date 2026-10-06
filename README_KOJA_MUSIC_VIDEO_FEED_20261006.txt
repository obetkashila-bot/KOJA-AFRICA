KOJA MUSIC — Vertical Video Feed Build — 2026-10-06

Public /music is now a full-screen vertical, video-first feed.
- One music video per screen; vertical scroll with snap.
- No description cards or catalogue cards.
- Like control on the left.
- Download control on the left; opens Video or Audio choice.
- Small title, artist and streamer count over the video.
- Only published + rights-verified tracks with an active signed licence and video_path appear.
- Playback and stream counters remain connected to KOJA MUSIC.
- Download is permitted only when the active licence has download_allowed=true.
- Mobile/data saver behavior keeps off-screen videos unloaded until needed.

Deploy:
1. Apply KOJA_MUSIC_MASTER_20261006.sql in Supabase if not already applied.
2. Apply KOJA_MUSIC_MASTER_20261006_VIDEO_FEED.sql.
3. Deploy app.py to Render with the existing production command.

Important: The feed does not create music rights. Only legally licensed and verified tracks can enter it.
