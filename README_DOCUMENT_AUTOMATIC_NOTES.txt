KOJA AFRICA — Documents Automatic Notes + In-Browser Reader

This package is an incremental upgrade of the current KOJA AFRICA app.py.

Included:
- Existing KOJA Document AI remains unchanged.
- Automatic document note generation in the background.
- Notes are generated from the actual document text.
- Notes are stored in Supabase in koja_document_automatic_notes.
- Content hashing detects document content/version changes and regenerates the note.
- Generated/updated timestamps are stored and shown.
- Show more / Show less for long automatic notes.
- Generation status is shown while a note is being prepared.
- Upload returns without waiting for AI note generation.
- Opening the Documents workspace also queues missing/stale notes.
- Existing Download action remains separate.
- Existing document viewer is preserved and improved so PDF, DOCX, TXT, MD, CSV and JSON can be read in-browser where supported.
- DOCX is converted server-side to a safe HTML reader view.
- Storage paths remain hidden from the browser.
- Existing Document AI / Ask KOJA AI flow is preserved.

Deployment:
1. Deploy app.py and requirements.txt to the existing KOJA-AFRICA Render service.
2. In Supabase SQL Editor, run KOJA_DOCUMENT_AUTOMATIC_NOTES.sql once.
3. Do not replace the existing database. The SQL migration is additive/idempotent.
4. Keep the existing KOJA environment variables and AI provider keys.

Important:
Background generation is process-based. If Render restarts before a note finishes, the next Documents page/open request will automatically queue the note again.
