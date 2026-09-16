KOJA GLOBAL BUSINESS V7 — COMPLETE BUSINESS CONNECT

This package extends the existing KOJA AFRICA single-file Flask application.

Files:
- app.py: latest KOJA app plus complete Business Connect V7 routes/UI/API.
- KOJA_GLOBAL_BUSINESS_V7_CONNECT.sql: additive Supabase migration.

Business Connect includes:
- Permanent KOJA Business Code
- Business-code lookup without exposing private data
- Connection requests
- Accept/reject/disconnect/revoke
- Connected Businesses
- Relationship types
- Per-business permissions
- Relationship contacts
- Relationship notes
- Relationship activity/audit trail
- Business relationship workspace
- Connect+ reuse
- API endpoints for integration with other KOJA modules

Deployment:
1. Run the SQL migration in the Supabase SQL Editor.
2. Replace the existing KOJA-AFRICA app.py with this app.py.
3. Keep the existing requirements.txt and environment variables.
4. Deploy to the existing KOJA-AFRICA Render service.

No existing KOJA service is intentionally removed by this package.
