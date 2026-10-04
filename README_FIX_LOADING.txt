KOJA AFRICA — AFRICA NOW STUCK LOADING FIX

Why this fix:
- AFRICA NOW could remain on the boot message if a worker's Supabase query returned no rows, even though another worker had collected stories.
- The API now merges available in-process emergency-cache stories when the database response is empty.
- The page shows an explicit retry message instead of leaving the original connection message forever.
- While empty, the page retries every 7 seconds; after stories appear, it refreshes every 60 seconds.
- The request does not wait for external news sources.

Deploy:
1. Replace your repository app.py with this package's app.py.
2. Keep requirements.txt unchanged unless your existing project requires a change.
3. Commit/push to the branch connected to Render and wait for deploy to finish.
4. Open https://koja-africa.onrender.com/nexus and refresh the page.
5. Test /api/nexus/africa-now?limit=20 directly. JSON should contain items and count > 0 once the cache is populated.

This package does not deploy to GitHub or Render automatically.
