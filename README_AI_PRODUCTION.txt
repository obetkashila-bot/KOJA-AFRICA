KOJA AFRICA - AI PRODUCTION IMPROVEMENT

This package keeps the existing KOJA AFRICA application and improves only the AI provider reliability layer.
Communications and other KOJA services were not intentionally changed.

AI fixes:
- Removed retired Groq Llama models from the built-in fallback list.
- Added current Groq production/system fallbacks: GPT-OSS 120B, GPT-OSS 20B, Qwen 3.6/3.8, Compound and Compound Mini.
- Added provider-specific output caps to reduce HTTP 413 oversized requests.
- A Groq HTTP 429 now moves to the next Groq model instead of stopping the whole Groq chain.
- An OpenAI HTTP 429 now moves to the next OpenAI model.
- A Gemini HTTP 429 now moves to the next Gemini model.
- Stable Gemini REST defaults are now Gemini 2.5 Flash and Gemini 2.5 Flash-Lite when Render environment variables are not set.
- Existing environment variables still take priority.
- Python syntax validation passed.

Deployment:
1. Replace the repository-root app.py with this app.py.
2. Keep the existing successful requirements.txt unless your repository already has a newer compatible one.
3. Keep the repository-root Procfile.
4. Commit and push to GitHub.
5. Let Render deploy automatically.
6. Test /health, then /ai-next.

Important:
- Do not put app.py inside a subfolder. It must be at repository root for gunicorn app:app.
- Do not commit API keys or .env files.
