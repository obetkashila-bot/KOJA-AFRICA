KOJA AFRICA CONNECT V8 — RECEIVER FIX

Base: current production app.py app(20260918-113649).py

Fixes the actual issue shown in Render logs: calls are created and WebRTC signaling is running, but the callee has no Connect incoming-call receiver/polling endpoint.

Added:
- GET /api/connect/incoming-calls — authenticated callee polling
- POST /api/connect/call/reject/<call_id>
- Global authenticated incoming-call banner on normal KOJA pages
- Answer link opens /connect/answer/<call_id>
- Decline control
- Existing Connect chat, call creation, offer, ICE, answer, check and end routes preserved
- Existing SQL schema preserved; no migration
- Other KOJA modules preserved

Deploy app.py only to the existing KOJA-AFRICA Render service.
