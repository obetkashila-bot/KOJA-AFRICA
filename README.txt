KOJA AFRICA CONNECT V11 — PUSH + CALL ROUTING FIX

Base: KOJA CONNECT V10.

Fixes:
1. notify_user() now actually sends native Android FCM through the existing relay.
2. Incoming Connect calls therefore trigger the existing native push path.
3. Web/VAPID push is optional and no longer prevents native push.
4. The notification settings page no longer falsely reports “Push service is not configured yet” when native Android push is the intended path.
5. Added /api/notifications/test-native-push for an authenticated test device.
6. /connect/call/ with no target now shows a useful Connect Call page instead of redirecting silently.
7. /connect/call/?conversation_id=...&mode=voice|video remains supported.
8. Existing WebRTC, ICE, TURN/STUN and Connect routes are preserved.
9. No destructive SQL changes.

Migration is unchanged from V10 and only creates the additive koja_fcm_devices table if needed.

IMPORTANT:
The Android app must register its FCM token at /api/notifications/fcm/register (or /api/push/register).
Render must have the existing FCM relay URL/secret configured.
