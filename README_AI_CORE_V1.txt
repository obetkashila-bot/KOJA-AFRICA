KOJA AI CORE V1 — Provider-Independent Engine

Scope: KOJA AI only. Communications and other KOJA services are not modified.

WHAT THIS ADDS
1. KOJA Core orchestration layer around the existing Memory V2 AI.
2. Local fallback for stored-memory retrieval, stored-file retrieval and safe arithmetic.
3. Provider-independent status endpoint: /api/nextgen/ai/core/status
4. Versioned learning ledger: /api/nextgen/ai/core/learn
5. Core knowledge store endpoint: /api/nextgen/ai/core/knowledge
6. Core task/evaluation/provider-health storage.
7. When external providers fail, KOJA Core can still perform supported local tasks instead of simply dying.

IMPORTANT DESIGN RULE
KOJA does not silently rewrite production Python code or deploy unreviewed code. The learning ledger stores knowledge, verified outcomes, task traces and diagnostics. Future self-building can propose changes and test them before controlled deployment.

DATABASE
Run KOJA_AI_CORE_V1.sql in Supabase SQL Editor after Memory V2 SQL. The migration is additive/idempotent and does not drop existing KOJA tables.

DEPLOY
Replace only the AI app.py with this package's app.py in the existing KOJA AFRICA Render project.
Start command remains: gunicorn app:app

OFFLINE BEHAVIOR
Without provider API keys, Core can still:
- retrieve prior KOJA AI conversations
- retrieve saved memories
- retrieve previously stored file text
- perform restricted arithmetic
- report its own Core capabilities/status

It will NOT pretend to be a general LLM when no language model is available. General free-form generation still requires a language model unless a future local model is installed.

NEXT STAGE
KOJA AI CORE V2 can add semantic/vector retrieval, a verified knowledge graph, tool registry, provider circuit breakers, automated evaluations, and a sandboxed change-builder that produces proposed patches without automatically deploying them.
