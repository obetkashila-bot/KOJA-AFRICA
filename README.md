# KOJA AFRICA Research Portal V6 — Render + Supabase Deployment

## 1. Supabase
1. Create/open a Supabase project.
2. Open SQL Editor.
3. Run `KOJA_AFRICA_DATABASE.sql`.
4. Create the Storage bucket configured by `SUPABASE_BUCKET` (default: `koja-files`) if your app requires uploads.
5. In Supabase Project Settings → API, copy the Project URL and service-role key.

## 2. Render
Create a new Web Service from this project/repository.
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`

## 3. Environment variables
Add the variables from `.env.example` in Render → Environment.
Do NOT commit real secrets to GitHub.

Required for Supabase-backed features:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

Required for AI research notes:
- `OPENAI_API_KEY` or `AI_API_KEY`

Optional:
- `SUPABASE_BUCKET`
- `AI_API_URL`
- `AI_MODEL`
- `SECRET_KEY`

## 4. Health check
After deployment, open:
`/health`

The response should indicate that the application is running.

## 5. Google indexing
After deployment, verify the live URL in Google Search Console and submit the sitemap if the application exposes it. Do not expect indexing immediately; Google must crawl and process the site.
