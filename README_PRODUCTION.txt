KOJA AFRICA — OAUTH HARDENED V3.1

This replacement hardens the Google/Facebook/GitHub OAuth flow for normal Chrome and Median Android/WebView/external-browser redirects.

Key changes:
- Server-side S256 PKCE remains enabled.
- OAuth transaction is stored in a dedicated short-lived Secure + HttpOnly SameSite=Lax cookie.
- Flask session remains as compatibility storage, but callback prefers the dedicated transaction cookie.
- Supports both normal OAuth ?state= and the Median-compatible ?oauth_state= fallback.
- State is compared with constant-time HMAC comparison.
- PKCE verifier is never placed in the callback URL.
- OAuth transaction cookie is deleted after completion/failure.
- Existing email/password authentication is untouched.
- Supported social providers: Google, Facebook, GitHub.

REQUIRED RENDER ENVIRONMENT:
- SECRET_KEY or FLASK_SECRET_KEY must be a stable, long random value and MUST NOT change between deployments/workers.
- SUPABASE_URL must be configured.
- SUPABASE_PUBLISHABLE_KEY or SUPABASE_ANON_KEY must be configured.

SUPABASE AUTH URLS:
Site URL: https://koja-africa.onrender.com
Redirect URL: https://koja-africa.onrender.com/auth/callback

Provider callback URLs remain the Supabase provider callback URLs shown by Supabase. Do not point Google/Facebook/GitHub directly at the Render callback unless Supabase explicitly instructs you to.

After deployment, the expected callback is:
/auth/callback?code=...&state=...
or, for browser paths that drop top-level state:
/auth/callback?code=...&oauth_state=...

If the flow fails after this build, inspect logs for:
- OAuth state mismatch
- OAuth callback missing PKCE code verifier
- Supabase PKCE exchange failed
- Supabase user lookup after OAuth failed

Do not disable PKCE.
