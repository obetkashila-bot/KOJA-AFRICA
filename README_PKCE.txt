KOJA AFRICA — Google + GitHub + Facebook PKCE OAuth

This package is based on the current KOJA AFRICA app and preserves the existing application.

OAuth callback URLs:
KOJA: https://koja-africa.onrender.com/auth/callback
Supabase provider callback: https://rarwbuhpajggduyptymt.supabase.co/auth/v1/callback

Supabase configuration:
1. Enable Google, GitHub and Facebook under Authentication > Providers.
2. Enter the provider client ID and secret in Supabase.
3. Add the KOJA callback URL to Supabase Authentication URL Configuration / Redirect URLs.
4. Configure Facebook/Meta with the Supabase callback URL shown by Supabase.
5. Render must contain SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY).

PKCE implementation:
- Supabase auth flowType is explicitly set to pkce.
- persistSession and autoRefreshToken are enabled.
- detectSessionInUrl is disabled because KOJA explicitly calls exchangeCodeForSession().
- The KOJA session bridge uses same-origin credentials.
- OAuth errors are displayed in the callback page for troubleshooting.

Deployment:
Replace the repository app.py with this app.py, keep requirements.txt and Procfile, commit/push to GitHub, and deploy on the existing Render service.
