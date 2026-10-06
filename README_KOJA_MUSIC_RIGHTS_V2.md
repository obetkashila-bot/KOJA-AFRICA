KOJA MUSIC RIGHTS + 100 SONGS — V2

Baseline:
- Flask KOJA AFRICA production application.
- Existing KOJA MUSIC public playback/feed layer preserved.
- Existing Admin Music controls preserved.

V2 additions/fixes:
- Rights verification now requires an actual verified rights/licence record before a track can be marked verified.
- Public catalogue continues to require active artist + published track + verified rights + usable media.
- Artist application route: /music/apply
- Admin 100-song readiness dashboard: /admin/music/100
- Rights Centre: /admin/music/rights
- Music Management: /admin/music
- Public Music: /music

Database:
Run KOJA_MUSIC.sql first if the base Music tables are not present, then run
KOJA_MUSIC_RIGHTS_100_SONGS.sql. Both migrations are intended to be additive.

Deployment:
Use app.py as the replacement application file. Keep the existing Render environment
variables and dependency configuration from the current production service.
