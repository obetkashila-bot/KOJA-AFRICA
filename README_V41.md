# KOJA AFRICA V41 — COPILOT

Version: `2026.09.05-V41-COPILOT`

V41 is built from the verified V39 communications baseline and adds a KOJA Copilot AI workspace.

## V41 additions
- KOJA Copilot interface available at `/copilot` for authenticated users.
- Seven operating modes: General Assistant, Research & Evidence, Study Coach, Assignment Coach, Document Analyst, Business Assistant, Action Planner.
- Research-capable requests can retrieve web, Wikipedia, OpenAlex, Crossref and KOJA document evidence through the existing research engine.
- AI answers use the existing server-side `AI_API_KEY` / `OPENAI_API_KEY`, `AI_API_URL`, and `AI_MODEL` configuration.
- No AI secret is exposed to browser JavaScript.
- Conversation context is kept in the current browser session and limited before being sent to the server.
- Lightweight per-user rate limiting protects the Copilot endpoint.
- Deterministic evidence fallback is shown when no AI provider is configured.
- Existing V39 communications, voice/video calls, group-call invitation flow, statuses, assignments, professional services, documents/research, delivery/GPS and admin functionality are preserved.

## Render
Build command:
`pip install -r requirements.txt`

Start command:
`gunicorn app:app`

## Required environment variables
- `SECRET_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY` (or `SUPABASE_KEY`)
- `SUPABASE_STORAGE_BUCKET` (default `koja-files`)

## AI environment variables
- `AI_API_KEY` or `OPENAI_API_KEY`
- `AI_API_URL` (default `https://api.openai.com/v1/responses`)
- `AI_MODEL` (set this to the model supported by the configured AI endpoint)

## Important capability note
KOJA Copilot is an AI application layer, not a newly trained foundation model. Its advantage is combining AI with KOJA research, documents, academic workflows, professional services, communication and delivery workflows.

## Validation
- Python compilation: passed
- Flask import: passed
- `/copilot` route registered: passed
- `/api/copilot` route registered: passed
