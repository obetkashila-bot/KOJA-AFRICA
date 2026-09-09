KOJA AFRICA V20 MASTER — V12 TO V20 COMPLETE ENGINE PACKAGE
Version: 2026.09.09-V20.1-COMPLETE-ENGINES

WHAT THIS PACKAGE DOES
This package keeps the existing KOJA V1-V11 application as the base and adds the complete visible application/database foundation for V12-V20. Communications is preserved and is not rebuilt.

ENGINE CHECKLIST
V12 SEARCH & DISCOVERY
- Universal search index
- Search history
- Source filtering foundation
- Market fallback search
- Result/event tracking
Needs for full scale: background indexer, PostgreSQL full-text/pg_trgm tuning, optional external web/search providers.

V13 ADS NETWORK
- Advertiser campaigns
- Placements
- Creatives
- Billing counters
- Impression/click event foundation
Needs for live advertising: ad-serving endpoint, frequency/targeting engine, fraud controls, verified billing, reporting and payment settlement.

V14 KOJA PAY
- Unified transaction record
- Payment intents
- Payment method references
- Ledger foundation
- Webhook event storage
- Payout foundation
- 2% platform-fee accounting in the V14 UI
Existing Flutterwave checkout is preserved; this layer does not replace it.
Needs for live money movement: Flutterwave/webhook signature verification, reconciliation, idempotency, payout provider integration and financial controls.

V15 CLOUD & DEVELOPER
- Cloud projects
- Secure hashed API keys
- One-time API-key display
- Usage metering table
- Deployment queue
- Developer infrastructure foundation
Needs for real cloud platform: worker/queue, container/build runner, object storage, domains, secrets manager, API gateway/rate limits and billing.

V16 INTELLIGENCE & ANALYTICS
- Cross-service event stream
- Revenue event foundation
- Dashboards
- Metrics foundation
- Alert foundation
Needs for scale: scheduled aggregation, warehouse/OLAP layer, charting, anomaly detection and alert delivery.

V17 IDENTITY & TRUST
- KOJA ID compatibility fields
- Verification level
- Identity document submissions
- Trust events
- Security event visibility
- Session/security foundation
Needs for high-assurance identity: approved KYC provider, document/OCR verification, liveness where lawful, recovery controls, audit policy and encryption/key management.

V18 WORKSPACE & ENTERPRISE
- Workspaces
- Memberships
- Roles foundation
- Workspace files/documents tables
- Tasks
- Invoices
- Enterprise contracts/seats
Needs for enterprise scale: granular RBAC/ABAC, collaboration editor, storage lifecycle, audit logs, SSO/SAML/OIDC, SCIM, enterprise billing and data retention.

V19 KOJA SUPER-APP
- Service registry
- Ecosystem links
- Cross-service workflows
- Notification foundation
- Unified transaction fabric
Needs for scale: event bus, workflow worker, service-to-service authentication, API gateway, retries/idempotency and notification providers.

V20 AUTONOMOUS AFRICA
- AI agents
- Agent runs/jobs
- Tool permission foundation
- Agent memory
- Human approval gate
- IoT devices/telemetry
- IoT command foundation
- Future infrastructure records
Needs for real autonomy: AI model router, durable job queue, sandboxed tools, policy engine, human approval service, secrets isolation, observability and device security. Consequential financial actions remain human-approved.

DEPLOYMENT
1. Supabase -> SQL Editor -> paste/run KOJA_V1_V20_ALL_IN_ONE.sql.
2. Keep existing data. The V12-V20 additions use idempotent CREATE IF NOT EXISTS / ADD IF NOT EXISTS patterns.
3. Replace the existing Render KOJA-AFRICA app.py with this package's app.py.
4. Keep the existing requirements.txt and Procfile.
5. Deploy to the existing Render KOJA-AFRICA Production service.
6. Login and open /engines.
7. Test /v12 through /v20.
8. Test /api/engines/status while logged in.

ENVIRONMENT
Keep your existing KOJA environment variables. Recommended engine variables are in KOJA_V12_V20_ENV.example.

AI PROVIDERS
The existing V8 AI router remains part of the application. It supports configured providers/fallbacks; see the existing AI README for the provider list and limits. Do not remove those variables.

SECURITY
- Do not put Supabase service keys, payment secrets, SMTP passwords or AI API keys in browser code.
- API key secrets are hashed in the database and displayed once after creation.
- Payment intents shown in V14 are not proof of successful payment; provider verification/webhook processing is required.
- V20 does not execute autonomous consequential financial actions from the web UI.

COMMUNICATIONS
Communications is preserved from the production baseline. Do not alter Communications when deploying this engine package.
