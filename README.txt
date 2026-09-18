KOJA AFRICA V13 — CALL PUSH BACKEND + BOOK RESEARCH

BASE:
Current production app.py app(20260918-113649).py

CHANGES:
1. Connect Voice/Video buttons in a chat now pass conversation_id and resolve the current chat recipient server-side.
2. Added /connect/call and /connect/call/ resolver so missing-target call URLs show a useful page instead of silently redirecting.
3. notify_user() now also sends native Android FCM through the existing KOJA relay using:
   FCM_RELAY_URL / KOJA_FCM_RELAY_URL / PUSH_RELAY_URL / FCM_RELAY_ENDPOINT
   and FCM_RELAY_SECRET.
4. Added FCM registration/status/test endpoints.
5. Added KOJA Book Research at /research/books using the Open Library Search API.
6. Research results include book metadata and legal read/borrow/public-download links where the source exposes them.
7. No bypass of publisher, library, DRM, lending, or copyright controls.
8. Existing modules remain in the same single app.py.

SUPABASE:
Run KOJA_V13_MIGRATION.sql once. It is additive/update-safe.

IMPORTANT ANDROID:
This fixes the backend native FCM sending path. A true locked-screen Answer/Decline full-screen call UI still requires the Android app's FirebaseMessagingService/IncomingCallActivity to interpret data.type=call and launch the native call screen. Do not assume the web app alone can create that native UI.

BOOK SOURCES:
Open Library is used for discovery. For public ebook results, KOJA may expose the source's public download location. Borrowable/restricted books remain linked to the source for authorized reading/borrowing.
