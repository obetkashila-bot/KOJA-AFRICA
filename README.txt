KOJA AFRICA CONNECT V2 — Calls + UI Upgrade
Base: KOJA V12 Business Commerce Operations

Includes:
- Improved Connect call UI
- Voice calls
- Video calls
- Mute/unmute
- Camera on/off
- Incoming-call polling and answer/decline controls
- Call history UI
- Connect theme toggle using KOJA existing theme preference
- Improved WebRTC signaling polling and connection state handling
- Existing Connect database tables preserved
- No SQL migration
- Connect only; Business and other modules preserved from V12

WebRTC still requires HTTPS and browser camera/microphone permission.
For networks where direct WebRTC cannot establish a peer connection, configure a TURN server using a future TURN integration; the current upgrade keeps public STUN fallback and does not invent TURN credentials.
