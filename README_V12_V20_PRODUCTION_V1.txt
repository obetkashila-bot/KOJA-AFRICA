KOJA AFRICA — KOJA Core Engines PRODUCTION INTEGRATION V1

BASE: Production Hardening V2

INCLUDED
- V12 Search / Discovery foundation
- V13 Ads Network foundation
- V14 Payment Intent orchestration over existing payment providers
- V15 Cloud / Developer metadata
- V16 Data Intelligence events
- V17 Identity & Trust foundation
- V18 Workspace + Enterprise foundation
- V19 Service Registry, ecosystem links and unified transactions
- V20 AI agents, IoT, autonomy, future infrastructure and unified revenue foundation
- V12→V20 user hub, admin dashboard, status API and engine-event API
- Existing Market, Business, Accounting, Delivery and Live functionality retained
- Communications is not modified

DEPLOY
1. Run KOJA_V12_V20_PRODUCTION_V1.sql in Supabase SQL Editor.
2. Replace app.py in the existing Render KOJA-AFRICA deployment.
3. Keep: gunicorn app:app
4. Keep existing environment variables.
5. After deployment, open /platform/v12-v20 while logged in.

IMPORTANT
This is a production foundation/integration layer. It does not claim that every V12–V20 concept is fully autonomous or globally deployed. Provider-specific integrations and operational controls are still required before activating real-world payment orchestration, AI-agent execution, IoT control, enterprise contracts or future infrastructure.


CORE ENGINE NAMING / ATTACHMENT UPGRADE
Production names: KOJA Discover, KOJA Ads, KOJA Pay, KOJA Cloud, KOJA Intelligence, KOJA Identity, KOJA Workspace, KOJA Ecosystem, KOJA Autonomous AI.
Internal V12-V20 labels remain only for migration/version tracking. Existing services are upgraded in place; Communications is untouched.
Security: API-key hashes, scopes, expiry/revocation fields and audit/service-event bridges are included. Raw API secrets are returned only at creation.
After running the SQL, use /platform/engines while logged in and /api/platform/core-status to inspect the core attachment map.

STEP 3 — KOJA CLOUD UI
- Added logged-in /platform/cloud page for API key creation and revocation.
- Added KOJA Cloud to the More menu.
- Existing API endpoints /api/cloud/keys and /api/cloud/keys/revoke remain the backend.
- No Communications routes were changed.

NOTIFICATION CENTER
- Added KOJA Notifications center with unread badge and polling.
- Added per-user notification preferences for Market, Deliveries, AI, Messages/Calls and System.
- Added browser/phone push subscription support through Web Push.
- Optional Render environment variables: VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CLAIMS_EMAIL.
- Push permission is enabled by the user from Notification Settings; no push is forced.
- Existing Communications functionality is not otherwise changed.


NOTIFICATION CHANNELS
- KOJA notifications now support in-app + browser/phone push + email + SMS.
- Email uses SMTP_HOST/SMTP_PORT/SMTP_USERNAME/SMTP_PASSWORD/SMTP_FROM/SMTP_TLS.
- SMS supports Africa's Talking via AT_USERNAME/AT_API_KEY/AT_SENDER_ID, or Twilio via TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER.
- APP_BASE_URL may be set for email links.
- Users can enable/disable Email and SMS from Notification Settings.
