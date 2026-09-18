KOJA AFRICA V11 — COMMERCE HUB DIRECT FIX

Fixes the exact error:
"This Business module is not available in this deployment yet."

Commerce Hub is now handled directly by the Business module dispatcher, so it
opens even when an older deployment has the dispatcher but has not registered
the endpoint in app.view_functions.

The full Commerce Hub routes remain in app.py.

No SQL migration.
Connect+ untouched.

Deploy app.py to the existing KOJA-AFRICA Render production service.
