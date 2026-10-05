KOJA MUSIC INDUSTRY LIFECYCLE BUILD

Added to the existing KOJA MUSIC app.py:
Artist -> Songwriter -> Producer -> Recording -> Rights -> Distribution -> Promotion -> Radio/Media -> Live Events -> Fans -> Monetisation -> Royalties -> Accounting.

New UI:
/music/industry-suite
/music/industry-suite/<module>
/api/music/industry-lifecycle

The lifecycle uses the existing KOJA MUSIC artist/release records and adds additive lifecycle tables for the downstream music-industry records.

Supabase:
Run KOJA_MUSIC_INDUSTRY_LIFECYCLE_20261005.sql in the Supabase SQL Editor before using the new record forms.

The migration is additive: it creates new lifecycle tables and indexes and enables RLS on those new tables. It does not drop or truncate existing KOJA MUSIC data.
