KOJA AFRICA — Render deployment speed/health-check fix

1. Replace your repository app.py with app_deploy_speed_fix.py renamed to app.py.
2. Commit and push.
3. Change Render Start Command to:
   gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 --graceful-timeout 30 --keep-alive 5
4. Redeploy.

Why:
- /health is now a zero-dependency fast health endpoint. Render no longer waits for a Supabase query during health checks.
- One Gunicorn worker avoids duplicate AFRICA NOW background collectors and reduces memory/network pressure on the free instance.
- AFRICA NOW still uses the Supabase source registry and refreshes feeds in background.
