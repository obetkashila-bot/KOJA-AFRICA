KOJA AFRICA - CONNECT INCOMING CALL FIX V5 - 2026-09-20

Render logs show the call is created successfully, but the recipient is not given a reliable direct answer screen. The notification was also opening the generic /connect/calls page.

Fixes:
1. Incoming call notification now opens /connect/answer/<call_id> directly.
2. The page now shows explicit Answer and Decline buttons.
3. Answer waits briefly for the caller's SDP offer if the push arrives before offer creation finishes.
4. Decline uses the existing reject endpoint.
5. Existing call signaling endpoints are preserved.
6. No intentional changes to Media, Marketplace, AI, Business, or other KOJA services.

No SQL migration is required.

Deploy by replacing app.py. Keep gunicorn app:app and existing environment variables.
