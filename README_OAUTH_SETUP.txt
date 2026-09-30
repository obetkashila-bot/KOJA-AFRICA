KOJA AFRICA — Terms + Google/Facebook/GitHub Login Update

This update preserves the existing KOJA email/password login and adds Supabase Auth social sign-in buttons for Google, Facebook and GitHub.

IMPORTANT: OAuth providers must be enabled/configured in the Supabase Dashboard. The Flask app does not contain provider client secrets.

1. Deploy app.py to the existing KOJA AFRICA Render service.

2. Render environment variables:
   SUPABASE_URL=your existing Supabase project URL
   SUPABASE_PUBLISHABLE_KEY=your Supabase publishable/anon key
   (The current app already uses these when configured.)

3. In Supabase Authentication > Providers, enable Google, Facebook and GitHub and enter each provider's client ID/secret.

4. In Supabase Authentication > URL Configuration, set the production Site URL to:
   https://koja-africa.onrender.com

   Add this exact redirect URL:
   https://koja-africa.onrender.com/auth/callback

   Supabase requires redirect URLs to be explicitly allowed. See the official Supabase redirect URL documentation.

5. For each provider, use the callback URL shown by Supabase under the provider settings. Do not invent a different callback URL. GitHub, for example, uses the Supabase Auth callback URL shown in Authentication > Providers.

6. Public legal pages added:
   https://koja-africa.onrender.com/privacy
   https://koja-africa.onrender.com/data-deletion
   https://koja-africa.onrender.com/terms

7. Facebook/Meta:
   The existing Meta app can be configured as the Facebook provider in Supabase. The Facebook provider's client ID/secret are entered in Supabase, not in the public Flask page.

8. Email/password login is preserved. Existing local KOJA profiles and the existing Supabase password compatibility path are unchanged.

9. OAuth behavior:
   Provider -> Supabase Auth -> /auth/callback -> browser exchanges PKCE code -> /auth/oauth/session -> Flask creates/loads the KOJA profile -> dashboard.

10. Security:
   Never put provider client secrets in HTML, JavaScript, GitHub, or the public app. Store them in Supabase's provider configuration/secret storage.
