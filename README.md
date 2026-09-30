# KOJA AFRICA — Terms Acceptance + Google OAuth PKCE Fix

## Included
- `app.py` — current KOJA AFRICA Flask application with Terms & Conditions acceptance and Google/Facebook/GitHub OAuth PKCE configuration.
- `requirements.txt` — Render dependencies.
- `KOJA_TERMS_ACCEPTANCE.sql` — additive Supabase migration for Terms acceptance records.
- `README.md` — deployment notes.

## Google OAuth / PKCE fix
The OAuth client now explicitly uses:
- `flowType: 'pkce'`
- `persistSession: true`
- `autoRefreshToken: true`
- `detectSessionInUrl: false`

The same PKCE configuration is used on both the OAuth-start page and `/auth/callback`, so the browser retains the code verifier and can exchange the returned authorization code.

Supabase's PKCE flow requires the authorization code and the matching code verifier from the same browser/device. The authorization code is also single-use and short-lived.

## Supabase setup
1. Run `KOJA_TERMS_ACCEPTANCE.sql` once in the Supabase SQL Editor.
2. In Supabase Authentication > URL Configuration, add:
   `https://koja-africa.onrender.com/auth/callback`
   to the Redirect URLs.
3. For Google, keep the Supabase Auth callback configured in Google Cloud:
   `https://YOUR-SUPABASE-PROJECT-REF.supabase.co/auth/v1/callback`
4. Redeploy the application on Render.

## Terms behavior
- Registration requires the unchecked Terms checkbox to be selected.
- Signed-in users who have not accepted the current Terms version are sent to Terms & Conditions.
- `I Agree` records the Terms version and acceptance time.
- `Disagree` does not record acceptance and signs the user out.

## Important PKCE testing note
Start Google sign-in in one browser tab and complete it in that same browser/device. Do not open the callback in another browser, incognito window, or different device. Do not start two OAuth sign-ins at the same time in separate tabs, because the PKCE verifier can be replaced.
