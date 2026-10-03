# KOJA AFRICA — PRODUCTION GO-LIVE RUNBOOK

## Deployment

1. Run the existing production SQL migrations.
2. Run `KOJA_GO_LIVE_ACTIVATION.sql`.
3. Configure `.env.production.example` values in Render/Supabase/provider consoles.
4. Deploy the application.
5. Open `/api/v1/core/final-readiness`.
6. Open `/api/v1/core/go-live`.
7. Complete the external gates in `GO_LIVE_EXTERNAL_ACTIVATION.md`.

## Verification commands

```bash
python -m py_compile app.py
```

Then verify:
- `/health`
- `/api/v1/core/readiness`
- `/api/v1/core/final-readiness`
- `/api/v1/core/go-live`
- `/admin/final-readiness`
- `/admin/go-live`

## Rollback

If a release fails:
1. stop enabling new regulated/payment features;
2. preserve logs and evidence;
3. rollback the application release;
4. do not blindly rollback database migrations;
5. reconcile payment/webhook state;
6. verify queues and idempotency;
7. rerun health and smoke tests;
8. document the incident.
