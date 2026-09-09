KOJA AFRICA V20 MASTER

Package contents
- app.py: master Flask application based on the current KOJA production baseline with visible V12-V20 engine pages.
- KOJA_V1_V20_ALL_IN_ONE.sql: consolidated additive database migration (V8 foundation + V12-V20 engine infrastructure).
- requirements.txt
- Procfile

Deploy to the EXISTING Render KOJA-AFRICA Production service. Do not replace the service with Railway.

Supabase
1. Open Supabase SQL Editor.
2. Run KOJA_V1_V20_ALL_IN_ONE.sql.
3. Keep existing data. The migration uses CREATE IF NOT EXISTS / ALTER IF EXISTS and idempotent seeds where possible.

Render
1. Replace the repository app.py with this app.py.
2. Keep the existing environment variables, especially SECRET_KEY, SUPABASE_URL and the Supabase service key.
3. Commit and deploy.
4. Render start command is supplied by Procfile: gunicorn app:app.

Visible engines
V12 Search & Discovery
V13 Ads Network
V14 KOJA Pay
V15 Cloud & Developer
V16 Intelligence & Analytics
V17 Identity & Trust
V18 Workspace & Enterprise
V19 KOJA Super-App
V20 Autonomous Africa

Communications
The existing Communications code is preserved and not redesigned by this package.

Important
V14 does not replace the existing Flutterwave checkout; it adds a unified transaction layer. V20 agents only queue tasks in this version; consequential financial actions should remain human-approved.
