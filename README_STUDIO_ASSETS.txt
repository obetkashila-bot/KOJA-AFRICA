KOJA NEWS STUDIO ASSETS

This package contains the complete app.py with the KOJA NEWS Studio Assets feature integrated into the current KOJA AFRICA application.

Features:
- Admin -> KOJA NEWS Studio Assets
- Upload JPG/PNG/WebP studio backgrounds and news desks to Supabase Storage
- Assign assets to KOJA NEWS scenes
- Select uploaded background and desk from KOJA NEWS Live Studio
- Public KOJA NEWS Live page uses the selected studio background and desk
- Existing KOJA NEWS/HLS/live studio functionality remains in app.py

Setup:
1. Run KOJA_NEWS_STUDIO_ASSETS.sql in the Supabase SQL Editor.
2. Ensure SUPABASE_URL and SUPABASE_SECRET_KEY/SUPABASE_SERVICE_KEY/SUPABASE_KEY are configured.
3. Ensure SUPABASE_STORAGE_BUCKET points to a bucket that allows the application's server-side upload and public object URLs. Default: koja-files.
4. Deploy app.py with the included requirements.txt and Procfile.
5. Open /admin -> NEWS STUDIO ASSETS.
6. Upload backgrounds/desks, then open NEWS LIVE STUDIO and select them.

For desk overlays, transparent PNG is recommended so the presenter/camera remains visible above the desk.
