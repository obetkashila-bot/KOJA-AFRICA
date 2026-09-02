KOJA AFRICA ASSIGNMENT FIX - 2026-09-03

Database repair required:
assignments.student_id must reference public.profiles(id).
The assignments status constraint must allow 'submitted'.

The included app.py:
- uses profiles.id for student_id and user_id
- validates the logged-in user ID
- inserts submitted assignments using the live schema
- stores assignment file metadata
- logs assignment creation
- creates a student notification
- falls back to user_id when loading assignments
- logs the exact database error instead of hiding it

Before deploying, confirm the Supabase SQL repair has been run successfully.
