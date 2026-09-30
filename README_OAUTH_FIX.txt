KOJA AFRICA — OAuth Fix

This build keeps the existing KOJA AFRICA security hardening and Supabase OAuth flow.
It includes Google, Facebook and GitHub login buttons and fixes the OAuth session bridge
so the short-lived Supabase bearer token is not blocked by the browser CSRF handoff.

Deploy:
- Replace app.py in the KOJA-AFRICA repository.
- Keep the existing Render start command: gunicorn app:app
- Keep the existing Supabase Auth provider configuration and redirect URL:
  https://koja-africa.onrender.com/auth/callback

No SQL migration is required for this OAuth fix.
