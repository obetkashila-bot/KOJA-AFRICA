KOJA AFRICA — AI MEMORY V2

Scope: AI ONLY. Communications and other KOJA services are intentionally untouched.

WHAT V2 FIXES
- /ai-next remains a self-contained shell and is rendered literally to avoid the Jinja template error caused by CSS/JavaScript braces.
- KOJA AI now retrieves relevant long-term memories for the signed-in user.
- KOJA AI searches persisted previous AI messages when the user asks about an earlier/previous chat.
- KOJA AI can retrieve recent chats when a direct message match is weak.
- Uploaded AI files can be stored as user-scoped extracted text so a later request such as "the file I gave you" can retrieve it when relevant.
- Both streaming and non-streaming next-generation AI endpoints use the memory layer.
- Natural explicit memory commands remain supported: "Remember that...", "From now on...", "Going forward...", and "Save this...".
- Memory API supports listing, searching and forgetting memories.
- /api/nextgen/ai/models is now a real route.

IMPORTANT PRIVACY DESIGN
- Memory and stored file content are scoped by the authenticated Supabase user ID.
- The AI prompt receives only retrieved relevant memory/file content, not another user's data.
- Stored files contain extracted text only; the original upload is not duplicated by this table.
- Users can deactivate one memory or all active memories through the memory DELETE endpoint.

DATABASE
Run KOJA_AI_MEMORY_V2.sql once in Supabase SQL Editor.
It is additive/idempotent and does not drop/recreate existing KOJA tables.

RENDER
Deploy the included app.py to the existing KOJA-AFRICA Render Production service.
The existing Procfile remains:
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120

TESTS
1. Login to KOJA.
2. Open /ai-next.
3. Ask: "Remember that KOJA is my project."
4. Start a new chat.
5. Ask: "What do you remember about my project?"
6. Ask: "What was our previous chat?" after several persisted AI conversations.
7. Upload a document, then in a new chat ask about the file.

V2 retrieval is deliberately lightweight and does not require a vector database extension. A future V3 can add embeddings/vector search, automatic memory confidence scoring, contradiction resolution, memory editing UI and richer file indexing.
