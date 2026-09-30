KOJA AFRICA - Terms + Google/Facebook/GitHub Login
===================================================

This package uses the supplied KOJA AFRICA app.py as the baseline. Existing
email/password authentication remains in place. The package includes:

- /terms
- /privacy
- /data-deletion
- Google OAuth
- Facebook OAuth
- GitHub OAuth
- Supabase PKCE OAuth callback
- Existing KOJA profile creation/linking

DEPLOYMENT
----------
Use the normal KOJA AFRICA Render deployment command:
    gunicorn app:app

SUPABASE ENVIRONMENT VARIABLES
------------------------------
Set these on Render (server environment):
    SUPABASE_URL=https://YOUR_PROJECT.supabase.co
    SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
    SUPABASE_PUBLISHABLE_KEY=YOUR_SUPABASE_PUBLISHABLE_KEY   (if used by your project)
    SUPABASE_SERVICE_KEY=YOUR_SERVICE_ROLE_KEY
    SECRET_KEY=YOUR_LONG_RANDOM_SECRET

Do not put OAuth provider client secrets in app.py. Google/Facebook/GitHub
client credentials belong in Supabase Authentication -> Providers.

SUPABASE AUTH PROVIDERS
-----------------------
Enable:
    Authentication -> Providers -> Google
    Authentication -> Providers -> Facebook
    Authentication -> Providers -> GitHub

SUPABASE REDIRECT URL
---------------------
Add this exact URL to Supabase Authentication -> URL Configuration -> Redirect URLs:
    https://koja-africa.onrender.com/auth/callback

The callback URL is also generated dynamically from the deployed application,
so a different production hostname will use that hostname's /auth/callback.

PROVIDER SETUP
--------------
Google:
- Create/configure the Google OAuth application.
- Put the Google Client ID and Client Secret in Supabase's Google provider settings.

Facebook:
- Create/configure the Meta/Facebook application.
- Configure the OAuth redirect/callback URL shown by Supabase for the Facebook provider.
- Put the Facebook App ID and App Secret in Supabase, not in Flask.
- Configure the Meta app's privacy policy and data deletion URLs to point to:
    https://koja-africa.onrender.com/privacy
    https://koja-africa.onrender.com/data-deletion

GitHub:
- Create/configure the GitHub OAuth application.
- Put the GitHub Client ID and Client Secret in Supabase's GitHub provider settings.

IMPORTANT
---------
The browser receives only the Supabase public/publishable key. Provider secrets
are never embedded in app.py. Supabase performs provider authentication and the
KOJA callback exchanges the authorization code using the Supabase JavaScript SDK
with PKCE enabled.

PUBLIC PAGES
------------
Privacy:       https://koja-africa.onrender.com/privacy
Terms:         https://koja-africa.onrender.com/terms
Data deletion: https://koja-africa.onrender.com/data-deletion
OAuth callback:https://koja-africa.onrender.com/auth/callback
