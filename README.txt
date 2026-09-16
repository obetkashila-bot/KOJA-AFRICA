KOJA AFRICA Services endpoint fix - 2026-09-16

Root cause:
The /services template called url_for('market'), but the actual Flask endpoint is koja_market for route /market. This caused BuildError and HTTP 500 on /services.

Fix:
Changed only the broken template reference from url_for('market') to url_for('koja_market').

No database migration. No service/module logic changed.

Deploy:
Replace the production app.py with this file and deploy normally to KOJA-AFRICA on Render.
