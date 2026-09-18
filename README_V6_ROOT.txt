KOJA AFRICA CONNECT V6 — ROUTE-SAFE CALLS

IMPORTANT: This package has app.py at the ZIP ROOT so Render/GitHub deployment can use it directly.

Connect call routes included:
GET  /connect/call/<user_id>?mode=voice|video
GET  /connect/call/answer/<call_id> (compatibility alias)
GET  /connect/answer/<call_id>
POST/GET /api/connect/call/ice/<call_id>
POST /api/connect/call/create
POST /api/connect/call/offer/<call_id>
GET /api/connect/call/check/<call_id>
POST /api/connect/call/answer/<call_id>
POST /api/connect/call/reject/<call_id>
POST /api/connect/call/end/<call_id>
POST /api/connect/call/heartbeat/<call_id>

Existing TURN variables are reused:
KOJA_TURN_URLS
KOJA_TURN_USERNAME
KOJA_TURN_CREDENTIAL

No SQL migration required.
