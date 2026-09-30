# KOJA AFRICA — Terms & Conditions Acceptance

This package contains the updated KOJA AFRICA Flask application with a visible Terms & Conditions acceptance flow.

## Files
- `app.py` — complete KOJA AFRICA Flask application
- `requirements.txt` — Python dependencies for Render
- `KOJA_TERMS_ACCEPTANCE.sql` — additive Supabase migration for recording Terms acceptance
- `README.md` — deployment instructions

## Supabase
Run `KOJA_TERMS_ACCEPTANCE.sql` once in the Supabase SQL Editor before using the Terms acceptance record system.

## Render
Build command: `pip install -r requirements.txt`
Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`

Keep the existing KOJA AFRICA environment variables, especially `SECRET_KEY`, `SUPABASE_URL`, and `SUPABASE_SECRET_KEY`.

## Terms flow
- Registration requires the user to check the Terms & Conditions agreement box.
- The Terms page provides `I Agree` and `Disagree` actions.
- Acceptance records the Terms version and acceptance time.
- Disagree does not record acceptance and prevents continued protected use where acceptance is required.
- Existing KOJA AFRICA features are preserved.
