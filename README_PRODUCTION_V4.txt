KOJA AFRICA — MEDIA STUDIO RELIABILITY V4

BASELINE
This package is based on KOJA AFRICA MEDIA DIRECT STORAGE V2 FIXED. The existing Netflix-style KOJA Media structure is preserved.

KEY FIXES
- Fixes the previous Studio Jinja syntax error.
- Direct browser-to-Supabase Storage upload; movie bytes do not pass through Render.
- Uses Supabase's signed resumable TUS route for browser uploads so the Flask service key is not exposed.
- Uses the current 6 MB TUS chunk size recommended by Supabase documentation.
- Direct Storage hostname is used automatically for Supabase projects.
- Upload preparation retries three times and reports the real server/network error.
- Upload status is explicit: preparing, uploading, verifying, saving.
- TUS resume/fingerprint support is preserved.
- Large-file TUS failure does not silently fall back to sending the movie through Render.
- Completion verification retries once and confirms the object before creating the media record.
- Signed PUT fallback remains available for files up to 100 MB.
- Existing 50 GB application-side limit is preserved; the actual Supabase plan/storage configuration still governs what can be uploaded.
- KOJA intro WAV is included in static/.

DEPLOY
Upload/deploy ALL files in this ZIP, not only app.py. The static/ directory is required for /static/koja-intro.wav.

REQUIRED ENVIRONMENT
Use the same production Supabase/Flask environment variables already used by KOJA AFRICA, especially SUPABASE_URL, SUPABASE_SERVICE_KEY, FLASK_SECRET_KEY, and any existing storage bucket settings.

IMPORTANT
Supabase recommends TUS resumable uploads for files larger than about 6 MB and supports pause/resume and progress reporting. The application-side 50 GB value is not a guarantee of storage-plan capacity.
