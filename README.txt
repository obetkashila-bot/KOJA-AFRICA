KOJA AFRICA SERVICES CUMULATIVE UI FIX

Base: app(20260915-070637).py

Changes:
1. Fixed /services BuildError: url_for('market') -> url_for('koja_market').
2. Reorganised /services so the visible page cumulatively shows KOJA Business, Learning and Research, Intelligence, Commerce/Marketplace, Finance/Payments, Supply/Delivery, Professional Services, Communication and Platform Engines.
3. Existing routes, database tables and Communications logic are untouched.
4. No SQL migration is required.

Deploy app.py to the existing KOJA-AFRICA Render production service.
