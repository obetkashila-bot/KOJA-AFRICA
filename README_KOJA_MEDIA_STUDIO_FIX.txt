KOJA AFRICA — REAL KOJA MEDIA + STUDIO FIX
Base: app(20260915-070637).py

WHAT THIS FIX ADDS
1. /media-next — KOJA Media feed remains connected to koja_public_posts.
2. /studio — authenticated KOJA Media Studio.
3. Media Studio supports photo/video upload, private drafts and publishing.
4. Published Studio media appears automatically in KOJA Media because both use
   the same koja_public_posts source of truth.
5. Basic impressions/completions are shown for the creator.
6. Media feed cards have stable #media-<id> anchors.
7. Existing Communications and other KOJA modules are not intentionally changed.
8. Upload limit remains 15 MB and uses the existing Supabase Storage helper.

DEPLOY
1. Replace the production app.py with the app.py in this ZIP.
2. Run KOJA_MEDIA_STUDIO.sql once in Supabase SQL Editor.
3. Keep the existing Render environment variables.
4. Deploy with the existing KOJA AFRICA Render command.

IMPORTANT
This is an additive Media/Studio patch. It does not recreate or delete existing
KOJA tables or media records.
