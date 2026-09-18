KOJA AFRICA CONNECT V12 — CHAT CALL RECIPIENT FIX

Base: KOJA Connect V11 Push + Call Fix.

Fix:
- Voice Call and Video Call buttons inside /connect/chat/<conversation_id>
  now pass the current conversation_id to the call resolver.
- The resolver obtains the other conversation member server-side and then
  opens the existing one-to-one WebRTC call page.
- This prevents /connect/call/?mode=video from being opened without a target.
- Existing V11 native FCM push fix is preserved.
- Existing call/WebRTC/ICE behavior is preserved.
- No SQL migration.
- No changes to Market, Business, AI, Research, Delivery, or other modules.

Deploy app.py to the existing KOJA-AFRICA Render web service.
