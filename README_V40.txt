KOJA AFRICA Communications V40 — Security + TURN Ready

Based on V39 Security Hardened.

Adds:
- Optional server-configured TURN support for WebRTC.
- STUN remains the default when TURN variables are not configured.
- TURN credentials are read from Render environment variables and are not hard-coded in app.py.
- All WebRTC call pages use the same server-provided ICE configuration.
- V39 security hardening retained.
- Chat sender remains right; receiver remains left.

Render environment variables:
KOJA_TURN_URL=turn:YOUR-TURN-HOST:3478
KOJA_TURN_USERNAME=your-turn-username
KOJA_TURN_CREDENTIAL=your-turn-password-or-credential

Do not put TURN credentials in HTML or JavaScript manually.

Important: this package is TURN-ready; a real TURN provider/server must still be configured in Render for relay connectivity. No provider credentials are included.
