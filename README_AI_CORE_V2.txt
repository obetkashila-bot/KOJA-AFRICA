KOJA AI CORE V2

Scope: AI only. Communications and all other KOJA services are intentionally untouched.

CORE V2 adds:
- Meaning-oriented semantic retrieval fallback for memories, knowledge and stored files.
- User-scoped knowledge graph relationships.
- Safe deterministic tools (calculator, word count, retrieval).
- Provider health circuit-breaker state with cooldown after repeated failures.
- Tool registry and controlled self-improvement proposals.
- Core V2 status reporting.

IMPORTANT:
This is provider-independent at the core layer, not a full replacement for a language model. Without providers KOJA can still retrieve stored information, files and knowledge, use safe tools and report its limits. General free-form generation still requires a language model unless a local model is installed.

SELF-BUILDING SAFETY:
KOJA may record learnings and propose improvements, but this version does not silently rewrite production Python, run arbitrary code, or deploy changes. Production changes remain controlled and reviewable.

DEPLOYMENT:
1. Run KOJA_AI_MEMORY_V2.sql if not already installed.
2. Run KOJA_AI_CORE_V1.sql if not already installed.
3. Run KOJA_AI_CORE_V2.sql.
4. In the existing KOJA AFRICA Render Production service, replace only app.py with this package's app.py.
5. Keep gunicorn app:app as the start command.
6. Do not change Communications or other KOJA services.

TESTS:
- Upload a document and ask KOJA to study it.
- Start a new chat and ask: "Do you remember the file I uploaded?"
- Ask: "What was our previous chat?"
- Ask: "What were we working on?"
- Test arithmetic such as: "Calculate 125 * 8".
- Open /api/nextgen/ai/core/status while signed in.

Future V3 can add true vector embeddings, stronger entity extraction, document chunk indexing, verified knowledge provenance, sandboxed code-change generation and automated evaluation pipelines.
