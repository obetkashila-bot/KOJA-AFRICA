KOJA AFRICA — Render deployment package

FILES
- app.py: complete Flask application with a guarded LiveKit import.
- requirements.txt: production dependencies, including the official livekit-api SDK.

RENDER SETTINGS
- Runtime: Python
- Build command: pip install -r requirements.txt
- Start command: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --graceful-timeout 30 --keep-alive 5

REQUIRED ENVIRONMENT VARIABLES
- SECRET_KEY (or FLASK_SECRET_KEY): a long, random secret value.

KOJA integrations also use existing environment variables such as SUPABASE_URL,
SUPABASE_SERVICE_KEY (or the supported key alias in app.py), and SUPABASE_ANON_KEY.
Set these in Render's Environment page using the values from your existing Supabase
project. Do not put secrets in this file or commit them to GitHub.

LIVEKIT
- This project imports `from livekit import api`; the official distribution is
  `livekit-api`, which is listed in requirements.txt.
- For live video, set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in Render.
- The app now handles a missing/broken SDK without crashing the whole Flask service;
  LiveKit token endpoints will return a controlled error until the SDK is installed.

DEPLOY STEPS
1. Replace the repository's app.py with this app.py.
2. Replace the repository's requirements.txt with this requirements.txt.
3. Commit and push both files to the production branch of KOJA-AFRICA.
4. In Render, confirm the build command and start command above.
5. Confirm SECRET_KEY or FLASK_SECRET_KEY exists in Render Environment.
6. Trigger a new deploy and inspect the newest deploy logs.

This package does not change Render settings or deploy automatically. Existing
Supabase schema, OAuth provider settings, and third-party credentials remain managed
in their respective dashboards.


OAUTH PKCE FIX — 04 OCTOBER 2026
- Social OAuth now uses server-side PKCE for Google, Facebook and GitHub.
- The Flask session stores the state and PKCE code verifier across the external provider redirect.
- /auth/callback validates state and exchanges the authorization code directly with Supabase Auth.
- This removes dependence on supabase-js localStorage/sessionStorage in the Median WebView/external browser flow.
- Keep PKCE enabled.

IMPORTANT RENDER ENVIRONMENT
- SECRET_KEY or FLASK_SECRET_KEY must be set and must remain stable across deploys.
- SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY) must be configured.
- If SECRET_KEY changes while a social login is in progress, restart the login from the beginning.

OAUTH PKCE HARDENED V3 — 04 OCTOBER 2026
- Hardened server-side PKCE for Median Android/external browser and normal Chrome.
- Google, Facebook and GitHub continue through Supabase Auth with S256 PKCE.
- OAuth state is generated with high entropy and stored in the Flask session.
- V3 additionally embeds the same transaction state into the Supabase redirect_to URL as oauth_state.
- The callback accepts the normal top-level state or the preserved oauth_state redirect parameter, then requires an exact constant-time match with the server session state.
- The PKCE verifier remains server-side and is never exposed in the URL.
- One-time OAuth transaction values are cleared after completion.
- Keep SECRET_KEY/FLASK_SECRET_KEY stable across Render deployments and workers.
- Supabase Site URL: https://koja-africa.onrender.com
- Supabase redirect URL: https://koja-africa.onrender.com/auth/callback (and ensure Supabase Auth allows the callback URL with its oauth_state query parameter if your project enforces exact redirect matching).
