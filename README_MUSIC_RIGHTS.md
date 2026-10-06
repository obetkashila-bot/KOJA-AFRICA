# KOJA MUSIC Rights + 100 Authorised Songs

This build preserves the selected KOJA AFRICA application and adds an additive KOJA MUSIC rights-control layer.

## Routes
- `/music` — public authorised Music feed and browser playback.
- `/admin/music` — Music Management: artist activation, track rights verification/publication and artist applications.
- `/admin/music/rights` — rights centre and 100-song progress.
- `/api/music/play/<track_id>` — play-event recording.
- `/api/music/rights/<track_id>` — admin rights verification endpoint.

## Publication gate
A track is public only when:
1. its artist is active/published/approved;
2. its track status is published/active;
3. `rights_status = verified`; and
4. a playable media URL exists.

## Data protection
Unverified music is not exposed through `/music`. Data Saver uses lazy media loading and stops off-screen audio/embeds.

## Legal requirement
A database flag does not create copyright permission. KOJA should publish a recording only after the applicable master and composition/publishing rights are cleared and the written agreement is stored/referenced.
