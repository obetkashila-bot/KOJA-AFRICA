KOJA AFRICA — Automatic Document Notes Reliability Upgrade

This ZIP is an incremental fix to the existing Documents system. It does NOT
replace the Documents workspace, KOJA Document AI, document reader, upload
flow, approval flow, or Show more / Show less note display.

WHAT WAS FIXED
1. Automatic-note jobs are now durable in Supabase instead of depending only
   on an in-process background thread.
2. Each running job receives a 5-minute lease. If Render restarts, the worker
   crashes, or a request dies, the next Documents request can recover the job.
3. Browser status polling no longer re-downloads/re-extracts the document on
   every poll while a job is generating. It reads the persisted job status.
4. Only one in-process worker is scheduled for the same document at a time.
5. Failed jobs become a visible failure state instead of staying in
   “Generating…” forever.
6. A “Try again” action was added for failed automatic notes.
7. Existing legacy “generating” rows without a lease are recoverable.
8. Automatic notes remain grounded in the actual extracted document content.
9. The generated timestamp and source-content hash remain stored.
10. Existing successful notes are preserved.

SUPABASE STEP
Run KOJA_DOCUMENT_AUTOMATIC_NOTES.sql once in the existing KOJA AFRICA
Supabase SQL Editor before or immediately after deploying this ZIP.

DEPLOYMENT
Keep the existing Render command and environment variables. Replace the
current app.py/ZIP contents with this version, deploy, then open Documents.
No new AI provider or separate worker service is required.

IMPORTANT
The existing KOJA Document AI endpoint and AI functionality are unchanged.
This upgrade only makes automatic document-note generation persistent,
recoverable and observable.
