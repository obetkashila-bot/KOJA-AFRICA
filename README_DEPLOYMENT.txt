KOJA AFRICA — Corrected Render Deployment Package

This package uses the actual current KOJA AFRICA app.py supplied for the deployment.
No application routes or database migrations were intentionally changed in this package.

Deployment fix:
- Added gunicorn to requirements.txt. This fixes: "gunicorn: command not found".
- Added the Python dependencies imported by the current app.py.
- Added .python-version with Python 3.13 for a stable Render runtime.
- Procfile uses the existing production Gunicorn command.

Render settings:
Build Command:
pip install -r requirements.txt

Start Command:
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --graceful-timeout 30 --keep-alive 5

Keep all existing Render environment variables unchanged, including SECRET_KEY,
Supabase credentials, OAuth credentials, SMTP settings, AI keys and LiveKit settings.

No Supabase SQL migration is required for the Gunicorn/dependency fix.
