KOJA MUSIC ADMIN BUILD — 2026-10-05

Built additively on the currently accessible KOJA AFRICA app baseline.

Admin entry:
  /admin/music

Studio entry:
  /music/studio  (administrator redirects to /admin/music)

Added:
- KOJA MUSIC Management link on main Admin Dashboard
- Add Artist / Edit Artist
- Add Release / Edit Release
- Artist publish/suspend/feature controls
- Release publish/reject/takedown/feature controls
- Rights Centre with verify/reject
- Submission Queue
- MUSIC Analytics
- Public MUSIC route and release playback page
- Artist Dashboard
- Non-destructive Supabase migration for required MUSIC fields/tables

Important:
- Run KOJA_MUSIC_ADMIN_NONDESTRUCTIVE_20261005.sql in Supabase before deploying if the MUSIC tables/columns are not already present.
- The application uses the existing KOJA Supabase REST/storage configuration.
- No commercial music is included.
