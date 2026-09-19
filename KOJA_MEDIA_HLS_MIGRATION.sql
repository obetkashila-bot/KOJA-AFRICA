-- KOJA MEDIA V6: additive, update-safe migration.
-- Run in Supabase SQL Editor. Does not recreate or drop existing tables.

alter table public.koja_public_posts add column if not exists media_hls_ready boolean default false;
alter table public.koja_public_posts add column if not exists media_hls_url text;
alter table public.koja_public_posts add column if not exists media_processing_status text default 'pending';
alter table public.koja_public_posts add column if not exists media_processing_error text;
alter table public.koja_public_posts add column if not exists media_duration double precision;
alter table public.koja_public_posts add column if not exists media_processed_at timestamptz;

create index if not exists koja_public_posts_media_hls_idx
on public.koja_public_posts(media_hls_ready, media_processing_status, created_at desc);
