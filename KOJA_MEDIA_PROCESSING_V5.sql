-- KOJA AFRICA Media Processing V5
-- Additive migration. Run in Supabase SQL Editor before enabling the worker.

alter table if exists public.koja_public_posts
  add column if not exists processing_status text default 'ready',
  add column if not exists processing_error text,
  add column if not exists processing_progress integer default 0,
  add column if not exists media_master_url text,
  add column if not exists processed_at timestamptz;

create index if not exists koja_public_posts_processing_idx
  on public.koja_public_posts(processing_status, created_at desc);

create table if not exists public.koja_media_processing_jobs (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null,
  source_path text not null,
  status text not null default 'queued',
  attempts integer not null default 0,
  progress integer not null default 0,
  output_path text,
  error text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists koja_media_processing_jobs_queue_idx
  on public.koja_media_processing_jobs(status, created_at);
create unique index if not exists koja_media_processing_jobs_post_unique
  on public.koja_media_processing_jobs(post_id);

-- Public HLS output bucket. The worker uses the Supabase service key to write objects.
insert into storage.buckets (id, name, public)
values ('koja-media-hls','koja-media-hls',true)
on conflict (id) do update set public=true;

-- Optional: allow public reads from the HLS bucket when using Supabase Storage policies.
do $$ begin
  create policy "KOJA HLS public read" on storage.objects
  for select to public
  using (bucket_id = 'koja-media-hls');
exception when duplicate_object then null; end $$;

-- Existing queued videos can be re-enqueued manually if needed:
-- insert into public.koja_media_processing_jobs(post_id,source_path,status)
-- select id,media_url,'queued' from public.koja_public_posts
-- where media_type='video' and media_url is not null and (media_master_url is null or media_master_url='')
-- on conflict (post_id) do nothing;
