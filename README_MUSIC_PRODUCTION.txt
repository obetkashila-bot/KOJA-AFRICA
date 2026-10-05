KOJA MUSIC GLOBAL — PRODUCTION PIPELINE

This build adds the production integration layer to KOJA AFRICA without replacing the existing application.

PUBLIC MUSIC
- /music remains the listener/discovery experience.
- Published + rights-approved tracks can stream.
- Audio and visual media use short-lived signed URLs for newly uploaded private media.
- Download permissions are controlled independently for Audio and Visual.

ARTIST WORKFLOW
- /music/dashboard
- Artist profile -> Add Release
- New secure upload route: /music/dashboard/upload/<artist_id>
- Upload cover artwork, audio, optional visual and optional rights/licence document.
- New audio/visual/rights files are stored in the dedicated private Supabase bucket: koja-music.
- Every new release starts pending_review and is not public.

SEPARATE MUSIC STUDIO
- /music/studio is the separate administrator MUSIC Studio.
- Review a track from the Studio queue.
- Verify rights documents.
- Approve/reject/suspend publication.
- Independently allow Audio and Visual downloads.
- Mark releases Featured.
- A release becomes published only when its tracks are published and rights-approved.

SUPABASE
1. Run KOJA_MUSIC_GLOBAL_PRODUCTION_NONDESTRUCTIVE_20261005.sql.
2. The migration is additive and does not remove existing records.
3. It creates the private `koja-music` Storage bucket only when absent.
4. Ensure Render has SUPABASE_SERVICE_KEY configured so signed URLs can be generated.

IMPORTANT
The application keeps the existing KOJA AFRICA upload limit. Large music-video files should be handled by a future resumable/chunked upload service rather than increasing the existing global request limit blindly.
