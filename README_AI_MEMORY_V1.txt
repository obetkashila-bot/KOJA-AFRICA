KOJA AI MEMORY V1

1. Deploy app.py with the existing KOJA AFRICA Render service.
2. In Supabase SQL Editor, run KOJA_AI_MEMORY_V1.sql once.
3. No existing KOJA tables are dropped or recreated.
4. In KOJA AI, users can say: "Remember that ..." or "From now on, ...".
5. Saved memories are user-scoped and are automatically retrieved when relevant to a later AI question.
6. GET /api/nextgen/ai/memory lists the signed-in user's active memories.
7. DELETE /api/nextgen/ai/memory with {"id":"..."} forgets one; without id it clears the user's active memories.

The /ai-next page is also rendered as a literal self-contained shell so its CSS/JavaScript braces cannot be interpreted by Jinja. This fixes the Render error: TemplateSyntaxError: Missing end of comment tag.

Scope: AI only. Communications and other KOJA services are not intentionally modified.
