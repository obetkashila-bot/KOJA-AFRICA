KOJA AFRICA — Automatic Document Notes

This package upgrades the existing KOJA AFRICA app.py with an additive automatic
document-notes layer.

Features:
- Notes are generated from the actual extracted document content.
- Existing KOJA Document AI remains unchanged.
- Upload does not wait for AI; generation runs in a daemon background worker.
- Each note stores a SHA-256 content/version fingerprint.
- If the source document content changes, the API detects the changed fingerprint
  and queues regeneration.
- generated_at records when the current note was generated.
- updated_at records the latest note record update.
- Manual regeneration endpoint is available for authorized document users.
- Existing document access controls are reused.

Deployment:
1. Replace the deployed app.py with the included
   KOJA_AFRICA_AUTOMATIC_DOCUMENT_NOTES_app.py, renamed to app.py.
2. Run KOJA_DOCUMENT_AUTO_NOTES.sql once in the Supabase SQL Editor.
3. Deploy/restart Render.

Endpoints:
GET  /api/documents/<document_id>/automatic-note
POST /api/documents/<document_id>/automatic-note/regenerate

The new table is additive and does not replace:
- documents
- koja_document_ai_index
- koja_document_ai_memory
- koja_document_learning_progress


UI update: Each document card now displays the AI-generated Automatic Note with a compact preview and Show more / Show less control. Notes load asynchronously so the Documents page remains responsive.
