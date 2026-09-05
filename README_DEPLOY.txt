KOJA AFRICA — COMPLETE DEPLOY PACKAGE
=====================================

Package contents
----------------
app.py                       Main Flask application
requirements.txt             Render/Python dependencies
.python-version              Python runtime selection
schema_public_media_news.sql Public news/media + professional public communication tables
.env.example                 Environment variable template — contains NO real secrets
README_DEPLOY.txt            Deployment instructions

Render settings
---------------
Runtime: Python 3
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app

IMPORTANT
---------
1. Do not put real API keys, Supabase service keys, SMTP passwords, or GSC JSON in GitHub.
2. Add those values only in Render Environment Variables.
3. Run schema_public_media_news.sql in Supabase SQL Editor before testing Public News/Media and Professional Public Communication.
4. This package is designed for the existing KOJA-AFRICA Render service and existing Supabase project.
5. Keep the existing Render service; do not create a second KOJA service just to deploy this package.

Main test URLs
--------------
https://koja-africa.onrender.com/
https://koja-africa.onrender.com/health
https://koja-africa.onrender.com/public
https://koja-africa.onrender.com/professional-communication
https://koja-africa.onrender.com/connect
https://koja-africa.onrender.com/research
