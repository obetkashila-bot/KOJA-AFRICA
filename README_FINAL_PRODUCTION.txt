KOJA AFRICA — FINAL PRODUCTION ALL-ENGINES PACKAGE
Version: 2026.09.11

BASE
- Full KOJA Flask application.
- Existing Market, Business/Business Intelligence, AI, Research, Documents,
  Assignments, professional services, Deliveries/Drivers and Digital Marketplace.
- Existing notification center and notification preferences/push foundation.
- Existing V12-V20 platform foundation.
- Existing named core-engine integration: Discover, Ads, Pay, Cloud,
  Intelligence, Identity, Workspace, Ecosystem and Autonomous AI.
- Existing KOJA Cloud API-key flow including immediate deletion of revoked keys.
- Existing delivery/driver core integration.

PROFIT
- KOJA Profit Engine unified revenue layer.
- AI credit wallet and purchase flow.
- Flutterwave Zambia mobile-money checkout and server-side verification.
- Unified profit revenue records and admin dashboard.

COMMUNICATIONS
- Communications/Connect+ was not rebuilt or intentionally changed in this release.

DATABASE
1. Open Supabase SQL Editor.
2. Run KOJA_AFRICA_FINAL_PRODUCTION.sql.
3. The migration is additive/idempotent and does not drop or truncate existing tables.

RENDER
- Replace app.py in the existing KOJA-AFRICA Render service.
- Keep the existing start command: gunicorn app:app.
- Deploy.

IMPORTANT
- Keep existing Supabase and Render environment variables.
- Do not enable real-money payments until Flutterwave credentials and a controlled
  test transaction have been verified.
- AI provider keys remain server-side environment variables.
