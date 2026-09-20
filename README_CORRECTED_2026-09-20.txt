KOJA AFRICA — FULL REGRESSION CORRECTION — 2026-09-20

BASE
This app.py is based on the complete 845 KB KOJA production baseline (app(20260919-142253).py), not the smaller Media V6 app.

WHAT WAS FOUND
1. The Media V6 app contained about 57 production functions/routes that were present in the complete app but absent from the V6 package. This included Global Business/B2B functions and Connect call functions such as incoming-call/reject/slash handlers.
2. The complete app's business and call function bodies matched the earlier baseline; the regression was the later package being built from a reduced app.
3. Media was the area intentionally changed: Media V6 adds the dedicated player, HLS URL handling, watch progress, and external live URL support.

WHAT THIS PACKAGE DOES
- Restores the complete production app first.
- Adds Media V6 player/HLS/live features on top of it.
- Restores Global Business/B2B and all existing Connect call routes from the complete production app.
- Adds optional TURN configuration endpoint /api/connect/ice-config without changing the existing call signaling/database routes.
- Preserves Marketplace, AI, Research, Deliveries, Payments, Connect, Business and other KOJA services.

DATABASE
Run KOJA_REGRESSION_RESTORE_MIGRATION.sql in the same Supabase project before relying on Global Business V5/V6, B2B V4, Media HLS progress/live tables. The migration is additive/update-safe and contains no DROP/RECREATE commands.

RENDER
Keep the existing KOJA-AFRICA production web service and gunicorn app:app command. Do not replace the service.

OPTIONAL CALL NETWORK IMPROVEMENT
For mobile/carrier networks, configure TURN in Render environment variables:
KOJA_TURN_URL=turn:YOUR_TURN_HOST:3478
KOJA_TURN_USERNAME=...
KOJA_TURN_CREDENTIAL=...
The app will still use Google STUN when TURN is not configured.

MEDIA HLS
HLS processing still requires the separate FFmpeg worker and its existing V6 migration/worker configuration. The Flask app will fall back to /public/media/<post_id> when HLS is not yet processed.

MAX_UPLOAD_MB remains 15 MB; it was not silently changed.
