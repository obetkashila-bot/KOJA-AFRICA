# KOJA AFRICA — Research Engine V3

KOJA Research Engine combines live web discovery, Wikipedia, OpenAlex, Crossref and KOJA document records into one research workspace. Retrieved evidence is deduplicated and ranked before AI synthesis.

## AI configuration
Set `OPENAI_API_KEY` (or `AI_API_KEY`) and `AI_MODEL`. The default model is `gpt-5.6-luna`. The API endpoint defaults to the OpenAI Responses API.

## Supabase
Set `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `SUPABASE_STORAGE_BUCKET` as required by the rest of KOJA.

## Run
`pip install -r requirements.txt`
`gunicorn app:app --workers 2 --threads 4 --timeout 120`

## Research API
`GET /api/research?q=your%20topic&style=apa`

The API returns ranked results, source numbers, in-text citations, references and an evidence-grounded AI answer.
