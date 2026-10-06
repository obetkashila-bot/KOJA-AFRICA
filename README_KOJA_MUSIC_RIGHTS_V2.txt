KOJA MUSIC RIGHTS ACQUISITION + LICENSING V2

Deployment baseline:
- app.py is based on the current KOJA production music-enabled app in the working build.
- Existing KOJA MUSIC playback, embedded/public music routes, artist onboarding, admin music and Data Saver behaviour are preserved.

New workflow:
1. Admin opens /admin/music/acquisition and manages artist/label prospects.
2. Artist/rightsholder applies and declares authority.
3. Approved artist submits recordings.
4. Admin records master/composition ownership and verification evidence.
5. Admin completes the eight-point rights checklist.
6. Admin uploads the signed licence and records licensor/signature details.
7. KOJA only publishes after the complete checklist AND an active signed streaming licence pass.
8. Rights can be revoked, which suspends public streaming.

SQL:
Run KOJA_MUSIC_MASTER_20261006.sql in Supabase. It is additive and includes the acquisition and verification V2 migration.

Important:
Software records evidence; it does not create copyright permission. KOJA must obtain the actual written rights/licence from the applicable rights holders and any required territorial/collective licences before publication.
