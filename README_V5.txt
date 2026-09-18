KOJA AFRICA — END-TO-END V5
Version: 2026.09.18-V5

V5 connects the remaining transactional KOJA modules to the existing E2E backbone.

CONNECTED MODULES
- KOJA Market
- KOJA Business POS / Online Store
- Professional Services
- KOJA B2B
- Global Import & Export
- Business Live / Training
- KOJA AI Credits / Profit Engine
- KOJA Delivery through existing fulfillment flows

NEW
- Universal E2E synchronization API
- Per-user synchronization
- Administrator synchronization across users
- Universal E2E dashboard at /e2e/universal
- Automatic post-flow source linking for B2B, Business Store and Global Trade
- E2E automation event audit trail
- Universal module registry

SAFE RULES
- Existing source modules remain the source of truth.
- Existing routes are wrapped only after their normal processing; their original response is preserved.
- Communications / Connect+ is not modified.
- SQL is additive/update-safe.
- No existing table is dropped or recreated.

MIGRATION ORDER
1. KOJA_E2E_V1_MIGRATION.sql
2. KOJA_E2E_V2_MIGRATION.sql
3. KOJA_E2E_V4_MIGRATION.sql
4. KOJA_E2E_V5_MIGRATION.sql

DEPLOY
Use app.py in the existing KOJA-AFRICA Render Production service.
Run the migrations in Supabase SQL Editor before using the new V5 synchronization features.
