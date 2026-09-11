KOJA AI CORE V3
================

AI-only upgrade on top of Memory V2 and Core V1/V2.

Adds:
- dependency-free hybrid semantic retrieval using hashed vector fingerprints plus lexical scoring
- stronger retrieval across memories, stored files and KOJA knowledge
- adaptive feedback/evaluation endpoint
- controlled self-improvement proposal endpoint
- lightweight automatic knowledge-graph relationship capture
- semantic cache table for future real embeddings
- provider circuit-breaker fields
- safe self-building: proposes and evaluates changes but never silently edits/deploys production code

Install SQL in this order:
1. KOJA_AI_MEMORY_V2.sql
2. KOJA_AI_CORE_V1.sql
3. KOJA_AI_CORE_V2.sql
4. KOJA_AI_CORE_V3.sql

Deployment:
- Existing KOJA AFRICA Render Production service only.
- Replace only app.py with this package's app.py.
- Keep gunicorn app:app.
- Do not change Communications or other KOJA services.

V3 endpoints:
GET  /api/nextgen/ai/core/v3/status
POST /api/nextgen/ai/core/v3/feedback
POST /api/nextgen/ai/core/v3/propose

Important:
V3 semantic retrieval is intentionally provider-independent. It is not a full neural embedding model. A future V4 can add pgvector/real embeddings while preserving the current tables and APIs.
