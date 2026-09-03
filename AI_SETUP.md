# KOJA AFRICA AI Integration

The Research Engine now uses the OpenAI Responses API for evidence-grounded research synthesis.

## Render Environment Variables

Add these in Render > your Web Service > Environment:

- `OPENAI_API_KEY` = your OpenAI API key
- `AI_MODEL` = `gpt-5.6-sol`
- `AI_API_URL` = `https://api.openai.com/v1/responses`

Do **not** put the API key inside `app.py`, `.env.example`, HTML, JavaScript, or a public GitHub repository.

## How it works

1. KOJA retrieves web, Wikipedia, OpenAlex, Crossref and KOJA document sources.
2. The retrieved source snippets are sent from the Flask backend to the AI API.
3. The AI is instructed to use only those supplied sources and cite them as `[1]`, `[2]`, etc.
4. If the AI service is unavailable or no key is configured, KOJA automatically shows source-based research highlights instead of breaking the search page.
5. The request uses `store: false` so the generated response is not stored by the API request.

## Security

The browser never receives the OpenAI API key. All AI calls are made server-side by Flask.
