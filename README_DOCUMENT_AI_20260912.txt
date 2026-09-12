KOJA DOCUMENT AI

This upgrade turns Documents into a document-aware KOJA AI workspace.

Features:
- Uploads can be text-indexed for KOJA AI.
- Each document has an "Ask KOJA AI" action.
- Quick actions: summarize, explain, findings, study questions, extract facts, find gaps.
- AI uses the selected document as primary context and says when the document does not support an answer.
- Private documents are restricted to their owner/admin; approved/public documents can be queried according to the existing document access rules.
- KOJA Research remains the research/citation layer.
- Existing general KOJA AI remains unchanged.
- If the optional AI index table is not migrated, KOJA AI falls back to reading the private document from Storage when possible.
- Scanned/image-only documents require OCR before their text can be queried.

SUPABASE:
Run the updated KOJA_DOCUMENTS_SCHEMA_HARDENING_20260912.sql in Supabase SQL Editor.

DEPLOY:
Replace app.py/requirements/Procfile in the existing KOJA-AFRICA Render Production service.
