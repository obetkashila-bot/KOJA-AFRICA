KOJA AFRICA PUBLISHING CHECKLIST

1. Upload app.py to the GitHub repository root.
2. Keep the filename exactly: app.py
3. Keep requirements.txt in the repository root.
4. Keep static/favicon.png.
5. Render start command: gunicorn app:app
6. Ensure SUPABASE_URL and SUPABASE_ANON_KEY are configured.
7. Keep SUPABASE_SERVICE_KEY configured server-side for database operations.
8. Database must have public.profiles.id referencing auth.users(id) ON DELETE CASCADE.
9. The existing on_auth_user_created trigger must execute public.handle_new_user().
10. Do not add another auth-user trigger that duplicates profile creation.
