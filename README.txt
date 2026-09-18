KOJA AFRICA CONNECT V10 — PUSH + PAGE NOT FOUND FIX

Base: production app(20260918-113649).py

FIXED
- Existing native Android FCM push path is now supported server-side.
- Existing FCM_RELAY_SECRET architecture is reused; no Firebase service-account JSON is embedded.
- FCM token registration endpoints:
  /api/notifications/fcm/register
  /api/push/register
  /api/notifications/register-device
- Incoming call payload includes type=call, call_id, mode and /connect/answer/<call_id>.
- Connect incoming-call receiver/banner polls /api/connect/incoming-calls.
- Decline endpoint: /api/connect/call/reject/<call_id>
- Compatibility routes: /connect/call/ and /connect/call for older links using conversation_id/user_id/callee_id.
- Existing Connect WebRTC/signaling/TURN/STUN is preserved.
- Existing browser VAPID push remains optional and separate.

SUPABASE
Run KOJA_CONNECT_V10_MIGRATION.sql once. It only creates the FCM device table/index.

RENDER
The native relay expects the existing secret:
FCM_RELAY_SECRET
and a relay URL in one of:
FCM_RELAY_URL, KOJA_FCM_RELAY_URL, PUSH_RELAY_URL, FCM_RELAY_ENDPOINT.

ANDROID
The installed Android app must register its current FCM token with:
POST /api/notifications/fcm/register
JSON: {"token":"<FCM_TOKEN>","platform":"android","app_version":"<VERSION>"}

IMPORTANT
This ZIP is the Flask/Connect fix. The native Android app must already contain its FCM MessagingService and incoming-call Activity to show a full-screen/locked-screen call UI. The server payload is now ready for those components.
