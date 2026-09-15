KOJA AFRICA FINAL PRODUCTION UI — SERVICES ROUTE FIX

Fixes the live Services 500 error caused by url_for('market').
The actual Flask endpoint for /market is 'koja_market', so the Services page now uses url_for('koja_market').

No database or SQL changes.
No Communications changes.
No service logic changes.

Deploy app.py with the existing Render command:
gunicorn app:app
