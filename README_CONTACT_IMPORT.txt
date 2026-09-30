KOJA AFRICA — Communication Contact Import

Preserves existing messaging, groups, status, calling and Find People routes.

1. Run KOJA_COMMUNICATION_CONTACTS.sql in Supabase SQL Editor.
2. Deploy app.py.
3. Phone Contacts uses the browser Contact Picker when supported and asks the user for permission.
4. Facebook uses Meta/Facebook OAuth. Set META_APP_ID and META_APP_SECRET (or FACEBOOK_APP_ID/FACEBOOK_APP_SECRET) in Render.
5. Configure this callback URL in the Meta app:
   https://koja-africa.onrender.com/connect/facebook/callback

Important: Facebook's current Graph API only exposes friends who are also using the app and available through the granted API permissions. KOJA does not scrape Facebook or request Facebook passwords.
