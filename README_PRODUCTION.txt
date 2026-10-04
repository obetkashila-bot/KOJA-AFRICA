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
