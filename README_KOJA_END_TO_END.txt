KOJA AFRICA — END-TO-END CORE UPGRADE

This package extends the current KOJA build without replacing the existing modules.

Added:
- KOJA Control Center (/koja)
- Universal Search (/koja/search)
- Saved items (/koja/saved and API)
- Help & Support with user tickets (/koja/support)
- Admin Support Center (/admin/koja/support)
- User preferences API (/api/koja/preferences)
- Content/user reporting API (/api/koja/report)
- Audit-ready core SQL tables
- KOJA Hub link in the existing navigation
- Admin support link

Existing systems remain in place: Global News, News Live Studio, Studio Assets, AI,
Media, Market, Digital Marketplace, Business, Connect+, Professional Communication,
Deliveries/Drivers, Research, Questions, Assignments, Documents, Notifications and
KOJA Cloud.

IMPORTANT LIVE BROADCAST NOTE:
The browser camera preview is still a local preview unless an actual encoder/stream
source produces a public HLS/WebRTC output. This package does not pretend that a
getUserMedia preview is a public broadcast. Existing HLS source playback remains
public.

Deploy:
1. Run KOJA_END_TO_END_CORE.sql in Supabase.
2. Replace the deployed app.py with the included app.py.
3. Keep the existing Render start command: gunicorn app:app.
4. Test /health, /koja, /koja/search and /koja/support after login.
