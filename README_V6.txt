KOJA AFRICA CONNECT+ V6 — ROUTE-SAFE CALLS

Base: Connect+ V5

Fix:
- Incoming-call UI previously linked to /connect/call/answer/<id>, while the canonical Flask route was /connect/answer/<id>.
- V6 corrects the UI link.
- V6 also provides a compatibility alias at /connect/call/answer/<id>, so older notifications/links continue to work.

Preserved:
- Voice and video calls
- TURN environment variables already used by Connect V5:
  KOJA_TURN_URLS
  KOJA_TURN_USERNAME
  KOJA_TURN_CREDENTIAL
- ICE signaling
- Answer/decline/end
- Call heartbeat
- Call history
- Connect themes/UI
- No SQL migration
- No changes to Business, Market, Professional Services or other modules.

Deploy app.py to the existing KOJA AFRICA Render service.
