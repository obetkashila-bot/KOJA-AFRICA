KOJA AFRICA - Assignment Workflow Fix

Features included:
- Student assignment upload (PDF, Word, TXT, images)
- Secure student assignment viewing/downloading
- Admin assignment management
- Admin browser preview of uploaded PDF/files
- Admin download of student assignments
- Admin written answers
- Admin answer PDF/Word/TXT upload
- Secure student answer download
- Admin-only access to all submissions
- Student-only access to their own files

Deployment:
1. Replace your Render app.py with this app.py.
2. Keep the existing environment variables.
3. Ensure the assignments table migration has been run in Supabase.
4. Deploy with: gunicorn app:app
