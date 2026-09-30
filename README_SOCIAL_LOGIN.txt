KOJA AFRICA — Google + Facebook + GitHub Social Login Fix

This package uses the actual current KOJA AFRICA app.py and the corrected
Render dependency setup. The OAuth flow has been hardened for Supabase PKCE:
- Google, Facebook and GitHub all use the same secure Supabase OAuth flow.
- Explicit PKCE/session persistence is enabled.
- Provider-specific scopes are requested.
- The callback now reports the actual browser-side OAuth error instead of
  silently returning to /login.
- The access token is bridged to the existing KOJA Flask session through
  /auth/oauth/session.
- Existing email/password authentication is preserved.

Supabase configuration required:
1. Authentication -> Providers -> Google: enabled and configured.
2. Authentication -> Providers -> Facebook: enabled and configured with
   Meta App ID/Secret.
3. Authentication -> Providers -> GitHub: enabled and configured with
   GitHub OAuth App Client ID/Secret.
4. Authentication -> URL Configuration / Redirect URLs should include:
   https://koja-africa.onrender.com/auth/callback
5. Keep the existing KOJA Supabase URL and public/anon key environment
   variables in Render.

For GitHub OAuth App:
Homepage URL:
https://koja-africa.onrender.com

Authorization callback URL:
https://rarwbuhpajggduyptymt.supabase.co/auth/v1/callback

For Facebook/Meta, the Supabase provider callback is the same:
https://rarwbuhpajggduyptymt.supabase.co/auth/v1/callback

Render:
Build command:
pip install -r requirements.txt

Start command:
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --graceful-timeout 30 --keep-alive 5
