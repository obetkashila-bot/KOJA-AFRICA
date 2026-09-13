KOJA AFRICA - PRODUCTION PACKAGE
Date: 2026-09-13

This package is based on the KOJA production application dated 2026-09-12.

Included:
- app.py: unified production Flask application
- requirements.txt: production dependencies, including livekit-api and document AI parsers
- Procfile: Render/Gunicorn start command
- KOJA_ALL_SQL_MASTER_20260912.sql: existing additive KOJA master migration

Changes in this build:
1. Added unified Document AI to the existing Documents module.
2. Document AI can summarize, extract key points, create study questions, explain, perform research analysis, rewrite, and answer questions from an uploaded document.
3. Document AI indexes extracted text in koja_document_ai_index when that table exists.
4. Document AI learning history is recorded in koja_document_ai_memory and koja_document_learning_progress when those tables exist.
5. Existing document access controls are preserved.
6. Related user-facing modules are grouped into unified service areas: Learning and Research; AI and Workspace; Professional Services; Market and Business; Delivery and Logistics; Communication.
7. Existing underlying routes/services are preserved rather than deleted.
8. UI emoji characters were removed from the Python application.
9. Communications/WebRTC/FCM code was not intentionally removed.
10. LiveKit dependency is explicitly included in requirements.txt.

Deployment target:
Existing KOJA-AFRICA Render production service.

Important environment variables remain managed in Render and are not stored in this package.
Required integrations include the existing Supabase, AI provider, payment, site URL, session secret, push, and LiveKit environment configuration used by KOJA.
