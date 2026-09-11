KOJA AFRICA - Production Fix

This package contains the corrected production app.py from the studied KOJA application.

Render:
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --graceful-timeout 30 --keep-alive 5

Required environment variables include:
- SECRET_KEY (or FLASK_SECRET_KEY)
- SUPABASE_URL
- SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_KEY / SUPABASE_KEY)

Do not commit .env or API keys.

Validation performed:
- Python AST/bytecode compilation passed.
- Flask object named `app` is present in app.py.
- No changes were made to Communications logic.
