# KOJA AFRICA — FINAL PRODUCTION GO-LIVE

This package is the consolidated KOJA AFRICA production-readiness and go-live build.

## Main files

- `app.py` — complete Flask application
- `requirements.txt` — Python dependencies
- `KOJA_AFRICA_FULL_PRODUCTION_GO_LIVE.sql` — consolidated Supabase production/go-live SQL
- `.env.example` — production environment variable template
- `FINAL_REACHING_CHECKLIST.md` — final engineering readiness checklist
- `PRODUCTION_GO_LIVE_RUNBOOK.md` — deployment and verification runbook
- `GO_LIVE_EXTERNAL_ACTIVATION.md` — external provider, licensing, testing and regulatory activation steps

## Deploy

1. Put these files in the KOJA AFRICA GitHub repository.
2. Configure the production environment variables in Render.
3. Run `KOJA_AFRICA_FULL_PRODUCTION_GO_LIVE.sql` in the production Supabase SQL Editor.
4. Deploy with Gunicorn, for example:

   `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --graceful-timeout 30 --keep-alive 5`

5. Check `/health`.
6. Check `/api/v1/core/go-live` and `/admin/go-live` after authentication.

## Important

The software cannot manufacture external approvals. Live payment credentials, provider contracts, licences, LiveKit production credentials, FX providers, backup/restore exercises, security testing, disaster-recovery exercises and country-specific regulatory registrations must be completed with the real providers/regulators and recorded as verified go-live gates.
