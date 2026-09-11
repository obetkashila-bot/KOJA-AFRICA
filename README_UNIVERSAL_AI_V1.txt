KOJA UNIVERSAL AI V1

This package upgrades the existing KOJA AI next-generation interface into a Universal AI workspace.

New AI modes:
- Universal AI
- Business
- Education
- University
- Research
- Coding
- Finance
- Agriculture
- Healthcare information
- Legal information
- Government
- Career
- Creative
- Data
- Technology
- Personal productivity

The selected mode changes the specialist system instructions while retaining the existing provider fallback, streaming, persistent chat history, research detection, and document-context pipeline.

No Communications, Delivery, Marketplace, or other non-AI service code was intentionally changed.

Existing environment variables remain supported. Recommended provider settings:
GROQ_MODEL=openai/gpt-oss-120b
GROQ_FALLBACK_MODELS=openai/gpt-oss-20b,qwen/qwen3.6-27b
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-flash-lite

Deploy with the existing Render service using the existing Gunicorn command in Procfile.
No new Supabase SQL migration is required for the Universal mode selector because it reuses the existing KOJA AI conversations/messages tables.
