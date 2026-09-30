KOJA AFRICA — OAuth PKCE FIX

This build explicitly configures Supabase JS OAuth to use PKCE.

Included:
- Google OAuth
- Facebook OAuth
- GitHub OAuth
- Supabase auth flowType: pkce
- Explicit authorization-code exchange at /auth/callback
- Existing KOJA local session handoff at /auth/oauth/session
- Existing security hardening preserved

Deploy app.py to the KOJA-AFRICA Render service.
Supabase Auth redirect URL:
https://koja-africa.onrender.com/auth/callback

Do not put a service-role key in browser-visible variables.
