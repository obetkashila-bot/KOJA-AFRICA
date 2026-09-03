# KOJA AFRICA Research Portal V6 — Render + Supabase Deployment

## Important fix
This package includes `python-dotenv`, which is required because `app.py` imports `load_dotenv`.

## 1. Supabase
1. Open your Supabase project.
2. Go to SQL Editor.
3. Open `KOJA_AFRICA_DATABASE.sql` and run it.
4. Confirm the required tables were created.
5. Create/confirm the Storage bucket used by the app (default: `koja-files`).

## 2. Render
Create/use a **Web Service** connected to the repository containing these files.

Build Command:
```bash
pip install -r requirements.txt
```

Start Command:
```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
```

The repository root must contain `app.py` and `requirements.txt`.

## 3. Render Environment Variables
Add these in Render → Service → Environment:

- `SUPABASE_URL` = your Supabase project URL
- `SUPABASE_SERVICE_KEY` = your Supabase service-role key
- `SUPABASE_BUCKET` = `koja-files` (or your actual bucket)
- `SECRET_KEY` = a long random secret
- `OPENAI_API_KEY` = your OpenAI API key (only if AI notes are enabled)
- `AI_API_KEY` = optional alias for the same AI key
- `AI_API_URL` = `https://api.openai.com/v1/chat/completions`
- `AI_MODEL` = `gpt-4o-mini`
- `SITE_URL` = your deployed KOJA URL

Do not commit real API keys or Supabase service keys to GitHub.

## 4. Deploy
After uploading/pushing the files:
1. Trigger **Manual Deploy → Deploy latest commit**.
2. Check the build log for successful installation of `python-dotenv`.
3. Check the runtime log for `Booting worker`.
4. Open `/health` to confirm the application responds.

## 5. If an old failed deployment is cached
Push a new commit containing the corrected `requirements.txt`, then deploy that commit. Render must run `pip install -r requirements.txt` again.
