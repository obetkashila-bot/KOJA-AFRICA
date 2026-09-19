-- KOJA Media V6: additive-only migration. No tables are dropped or recreated.
alter table public.koja_public_posts add column if not exists media_processing_status text default 'pending';
alter table public.koja_public_posts add column if not exists media_master_url text;
alter table public.koja_public_posts add column if not exists media_duration_seconds numeric;
alter table public.koja_public_posts add column if not exists media_source_width integer;
alter table public.koja_public_posts add column if not exists media_source_height integer;
alter table public.koja_public_posts add column if not exists media_processed_at timestamptz;
alter table public.koja_public_posts add column if not exists media_processing_error text;
alter table public.koja_public_posts add column if not exists media_subtitles_url text;

create index if not exists koja_public_posts_media_processing_idx
on public.koja_public_posts(media_type, media_processing_status, created_at desc);

create table if not exists public.koja_media_watch_progress (
 id uuid primary key default gen_random_uuid(),
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 user_id uuid not null,
 session_id text,
 position_seconds numeric not null default 0,
 duration_seconds numeric not null default 0,
 updated_at timestamptz default now(),
 unique(post_id,user_id)
);
create index if not exists koja_media_watch_progress_user_idx
on public.koja_media_watch_progress(user_id, updated_at desc);
create index if not exists koja_media_watch_progress_post_idx
on public.koja_media_watch_progress(post_id, updated_at desc);

-- Optional subtitles are stored as a WebVTT public URL in media_subtitles_url.
-- The HLS worker creates media_master_url after successful processing.
