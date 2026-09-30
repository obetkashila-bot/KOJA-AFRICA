KOJA AFRICA — Automatic AI Document Notes

What was added
- Every uploaded document can automatically receive a short AI Quick Note.
- The note is generated from the document itself, not from unrelated knowledge.
- The original document is never replaced.
- KOJA checks the document updated_at value and regenerates the note when the source version changes.
- The note records generated_at/updated_at so the interface can show when it was last refreshed.
- Generation runs in a background thread so the document upload/library request does not wait for the AI response.
- A manual POST endpoint is also available:
  /documents/<document_id>/auto-note

Installation
1. Open the Supabase SQL Editor for the KOJA AFRICA project.
2. Run KOJA_DOCUMENT_AUTO_NOTES.sql once.
3. Deploy the included app.py.
4. Upload a document. KOJA will prepare the AI Quick Note automatically.

Important
- The existing document AI routes remain available.
- If the migration has not been run, the rest of the document system still works; only automatic notes remain disabled.
- AI generation requires the same configured KOJA AI provider environment variables already used by the application.
