KOJA AFRICA Research V7 Fix

Fixes the Render 500 error:
BuildError: Could not build url for endpoint 'research_view'

Cause:
The V7 Research template called research_view, but the route was missing.

This patch restores the KOJA Research Reader route and its safe public-source
HTML/PDF fetcher. It also blocks localhost/private/link-local/reserved targets
to reduce SSRF risk.

No SQL migration.
No changes to non-Research services.

Deploy app.py to the existing KOJA-AFRICA Render production service.
