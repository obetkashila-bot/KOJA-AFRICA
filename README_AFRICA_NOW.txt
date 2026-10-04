KOJA NEXUS — AFRICA NOW

What was added:
- A single AFRICA NOW screen at the very top of KOJA NEXUS.
- Automatic Africa-focused feed collection.
- Automatic ranking by freshness and importance signals.
- Server-side refresh every 5 minutes by default.
- Browser refresh every 5 minutes without manual page refresh.
- Story/source links and image/video media when the source feed supplies them.
- API endpoint: /api/nexus/africa-now

Deployment:
1. Run KOJA_NEXUS_AFRICA_NOW.sql in Supabase SQL Editor.
2. Replace the production app.py with the app.py in this package.
3. Deploy to the existing KOJA AFRICA Render service.

Optional Render environment variables:
KOJA_NEXUS_AFRICA_NOW_ENABLED=true
KOJA_NEXUS_AFRICA_NOW_INTERVAL=300

300 seconds = 5 minutes. The code enforces a minimum of 60 seconds.

The screen links users to the original source. KOJA does not claim to be the publisher
of third-party stories or live streams.
