KOJA ENTERPRISE V2
==================

This package is cumulative from the KOJA Sales & CRM V2 production source.
It preserves existing KOJA services and adds the Enterprise / Organizations V2 governance layer.

Enterprise V2 adds:
- Organization foundation compatibility
- Departments, employees, roles, workspaces, contracts, approvals, documents and billing foundation
- Multi-location / branch management
- Cross-functional teams
- Controlled member invitations
- Approval decisions
- Enterprise audit view
- Enterprise V2 summary API
- Additive/update-safe SQL migration

SQL migration:
KOJA_ENTERPRISE_V2.sql

Application:
app.py

Deployment order:
1. Run KOJA_ENTERPRISE_V2.sql in Supabase SQL Editor.
2. Confirm it completes successfully.
3. Deploy app.py to the existing KOJA AFRICA Render Production service.

No DROP, TRUNCATE or table recreation is used by the migration.
Communications and existing KOJA services are preserved.
