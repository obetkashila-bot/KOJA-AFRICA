KOJA AFRICA CONNECT+ V4 — RELIABLE CALLS + EXISTING TURN

Base: Connect V3.

V4 keeps the existing KOJA TURN configuration and applies it to BOTH caller and callee:
KOJA_TURN_URLS=turn:SERVER:3478,turns:SERVER:5349
KOJA_TURN_USERNAME=USERNAME
KOJA_TURN_CREDENTIAL=CREDENTIAL

Improvements:
- Existing STUN remains as fallback.
- Existing TURN is now actually included in the Connect+ RTCPeerConnection on both sides.
- Voice-call answer screen uses audio output instead of forcing a video-only layout.
- Mute and camera controls are available during calls.
- 60-second ringing timeout prevents stale calls.
- Connection-state recovery attempts ICE restart after temporary disconnect.
- Existing ICE signaling, incoming calls, answer/decline, call history and themes preserved.
- No SQL migration.
- Connect-only change; other KOJA modules are not modified.

Validation:
- Python syntax compiled successfully.

Production requirement:
The Render service must have the same KOJA_TURN_* environment variables used by the existing Professional Calls setup. Static syntax validation cannot prove real carrier/NAT call success.
