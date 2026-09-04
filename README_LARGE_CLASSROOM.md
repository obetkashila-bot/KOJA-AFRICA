KOJA AFRICA — LARGE CLASSROOM (SFU)

This upgrade replaces the browser-to-browser mesh classroom with a scalable LiveKit SFU classroom.

RENDER ENVIRONMENT VARIABLES REQUIRED:
LIVEKIT_URL=wss://YOUR-PROJECT.livekit.cloud
LIVEKIT_API_KEY=YOUR_API_KEY
LIVEKIT_API_SECRET=YOUR_API_SECRET
KOJA_LIVE_MAX_PARTICIPANTS=500   (optional)

SUPABASE:
Run teacher_large_classroom.sql once in Supabase SQL Editor.

PYTHON:
PyJWT is included in requirements.txt. Redeploy after updating the repository.

LARGE-CLASS DESIGN:
- Teacher publishes camera/microphone/screen through LiveKit.
- Students are subscribe-only for media by default, but can send reliable Q&A/raise-hand data.
- LiveKit SFU forwards media efficiently instead of creating a peer connection between every pair of students.
- Adaptive stream and dynacast reduce bandwidth/CPU usage.
- The backend issues short-lived room tokens; API secrets never reach the browser.

For very large public events, use LiveKit Cloud or a properly provisioned self-hosted LiveKit deployment with TURN/ICE, monitoring, recording/egress and capacity planning.
