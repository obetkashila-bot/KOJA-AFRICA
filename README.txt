KOJA AFRICA CONNECT V9 — CALL PUSH UPGRADE

Base: current production app.py app(20260918-113649).py

This version reuses the existing KOJA push notification system and upgrades
Connect call notifications to carry call_id and incoming-call type data.

Added:
- incoming call push payload includes call_id/related_id
- Connect voice/video and group-call notifications are marked as call pushes
- service-worker call notification uses persistent notification behavior
- Answer and Decline actions
- Answer opens /connect/answer/<call_id>
- Decline calls /api/connect/call/reject/<call_id>
- existing web incoming-call receiver remains available
- existing call creation, WebRTC signaling and database schema preserved
- no SQL migration
- no other KOJA module changes

IMPORTANT:
The existing native Android FCM incoming-call project can consume the same
call_id/call type. This backend does not replace the existing push relay.
For true Android locked-screen native full-screen calling, merge the existing
KOJA-AFRICA Android files (KOJAFirebaseMessagingService.java and
IncomingCallActivity.java) with this backend version. The backend payload now
contains the call identifiers needed by that receiver.

Deploy app.py to the existing KOJA-AFRICA Render service.
