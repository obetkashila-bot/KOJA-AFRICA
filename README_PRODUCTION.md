# KOJA AFRICA Production Reliability V3

This package keeps the existing KOJA AFRICA architecture and Media Direct-to-Storage flow, while adding a reliability foundation instead of replacing the existing application.

## Included
- Full `app.py`
- `static/koja-intro.wav`
- `requirements.txt`
- `Procfile`
- Production deployment notes

## Reliability changes
- Safe retry/backoff for idempotent Supabase GET/HEAD/OPTIONS requests.
- Mutation requests are not automatically retried, preventing accidental duplicate writes/payments.
- Request IDs with `X-Request-ID` response headers.
- Slow-request timing diagnostics.
- API-friendly JSON 404/500 responses.
- `/health` liveness endpoint.
- `/ready` readiness endpoint with a lightweight Supabase/profile-table probe.
- Existing CSRF, rate limiting, security headers, audit/idempotency and direct Media Storage logic preserved.
- Existing Media Studio direct resumable uploads preserved.

## Deploy on Render
1. Extract this ZIP.
2. Replace the production repository `app.py` with this `app.py`.
3. Make sure `static/koja-intro.wav` is committed at exactly `static/koja-intro.wav`.
4. Commit and push to the KOJA AFRICA production branch.
5. Render should build with the included `Procfile` or the service's configured Gunicorn command.
6. Verify:
   - `/health` returns HTTP 200.
   - `/ready` returns HTTP 200 when Supabase and `profiles` are available.
   - `/studio` loads without a Jinja error.
   - `/static/koja-intro.wav` returns HTTP 200.

## Required production environment
At minimum:
- `SECRET_KEY` (strong random value)
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY` or `SUPABASE_SECRET_KEY`

If using payments/media/communications, keep the existing KOJA environment variables configured as required by those modules.

## Important
This V3 is a reliability foundation, not a claim that every business feature is magically production-complete. Payments, licensing, media transcoding/CDN, 24/7 broadcast workers, marketplace operations, delivery operations and external provider accounts still depend on their respective services and database configuration.
