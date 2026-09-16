KOJA AFRICA — Assignments & Documents V2

Adds/strengthens:
- Student assignment file upload.
- Student download of submitted assignment files.
- Student download of admin answers.
- Admin assignment management with written answers and PDF answer upload.
- Admin Document Center for writing documents, uploading document files, publishing them, and downloading them.
- Admin written-document TXT download.
- Additive SQL migration for assignment/document file and answer fields.

Preservation:
- Existing Flask routes and services preserved.
- Communications is not intentionally modified.
- No tables are dropped or recreated.
- Existing Supabase storage configuration is reused.

Deployment:
1. Run KOJA_ASSIGNMENTS_DOCUMENTS_V2.sql in Supabase SQL Editor.
2. Replace app.py in the existing KOJA-AFRICA Render service.
3. Keep existing environment variables unchanged.
4. Test /health, /assignments, /documents, /admin/assignments and /admin/documents.
