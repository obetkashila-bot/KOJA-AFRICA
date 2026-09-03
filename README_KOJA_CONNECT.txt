KOJA AFRICA — KOJA CONNECT

Added to the latest KOJA AFRICA research/production application:
- KOJA Connect navigation
- User search and connection requests
- Direct chat with 2.5-second polling
- Voice-message recording/upload (webm, max 5 MB)
- Voice calls and video calls with WebRTC signaling
- 2-minute caller timeout and spoken network-unavailable message
- Incoming call answer page
- 24-hour text status
- Call history
- Private conversation membership checks
- Notification records for connection requests and calls

IMPORTANT DATABASE STEP
1. Open Supabase SQL Editor.
2. Paste and run KOJA_CONNECT.sql.
3. Redeploy this package to Render.

The app does not execute database DDL automatically. This avoids startup failures.

WEBRTC NOTE
The implementation uses Google STUN. Some networks require a TURN server for reliable production calls. Add TURN credentials later for broader NAT/firewall compatibility.

Existing KOJA features are preserved in app.py; this is an integrated single-file application.
