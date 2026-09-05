# KOJA AFRICA V39 — Reconstructed Package

This is the reconstructed V39 package based on the latest KOJA AFRICA Flask application in the user's library, with the KOJA Connect communications baseline preserved.

## Included
- `app.py` — complete Flask application
- `requirements.txt` — Render/Python dependencies
- KOJA Connect: direct chat, contacts, voice messages, voice/video calling UI and WebRTC signaling, status/notifications
- Assignments and answer approval workflow
- Professional Services and communication
- Documents / Research
- Delivery and live GPS functionality from the current baseline
- Admin approval and Google Search & Distribution/SEO functionality

## Required Render environment variables
- `SECRET_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY` (or `SUPABASE_KEY`)
- `SUPABASE_ANON_KEY` (optional where service key is sufficient)
- `SUPABASE_STORAGE_BUCKET` (default: `koja-files`)
- Payment/email/search-console variables only if those integrations are enabled.

## Start command
`gunicorn app:app`

## Important
V39 is reconstructed, not recovered from a file explicitly named V39. The source baseline used was the latest library application plus its KOJA Connect and final-schema features.
