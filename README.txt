KOJA AFRICA CONNECT V7 - ROUTE SAFE

This patch is based on the current production app.py.
It fixes the observed production error:
GET /connect/call/?mode=video -> 404

The chat call buttons now preserve conversation_id when a direct member cannot be resolved at template render time. The new /connect/call/ compatibility route resolves the other participant from koja_conversation_members and redirects to the existing call route.

No SQL migration.
No other KOJA modules intentionally changed.

Deploy app.py to the existing KOJA-AFRICA Render service.
