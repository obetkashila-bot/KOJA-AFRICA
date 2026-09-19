-- KOJA MEDIA V6 — additive migration only
-- Run in Supabase SQL Editor. Does not recreate or drop existing tables.

alter table if exists public.koja_public_posts
  add column if not exists media_hls_url text;

alter table if exists public.koja_public_posts
  add column if not exists media_master_url text;

alter table if exists public.koja_public_posts
  add column if not exists media_processing_status text default 'ready';

alter table if exists public.koja_public_posts
  add column if not exists media_processing_error text;

alter table if exists public.koja_public_posts
  add column if not exists media_duration_seconds numeric;

alter table if exists public.koja_public_posts
  add column if not exists media_processed_at timestamptz;

alter table if exists public.koja_public_posts
  add column if not exists subtitle_url text;

create table if not exists public.koja_media_processing_jobs (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.koja_public_posts(id) on delete cascade,
  status text not null default 'queued',
  attempts integer not null default 0,
  error_message text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);

create index if not exists koja_media_processing_jobs_status_idx
  on public.koja_media_processing_jobs(status, created_at);

create unique index if not exists koja_media_processing_jobs_post_active_idx
  on public.koja_media_processing_jobs(post_id)
  where status in ('queued','processing');

-- HLS worker needs access through the Supabase service key. Keep this table
-- inaccessible to anonymous clients unless your existing security model requires otherwise.
