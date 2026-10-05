-- KOJA MUSIC INDUSTRY LIFECYCLE
-- Additive migration. Creates lifecycle records without deleting or replacing
-- existing KOJA MUSIC tables/data.
-- Flow:
-- Artist -> Songwriter -> Producer -> Recording -> Rights -> Distribution ->
-- Promotion -> Radio/Media -> Live Events -> Fans -> Monetisation ->
-- Royalties -> Accounting

create extension if not exists pgcrypto;

create table if not exists public.koja_music_songwriters (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  name text not null,
  email text,
  publisher text,
  share_percent numeric(7,4),
  status text default 'draft',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_producers (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  name text not null,
  email text,
  role text default 'Producer',
  fee numeric(14,4),
  royalty_percent numeric(7,4),
  status text default 'draft',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_recordings (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  track_id uuid,
  title text not null,
  master_url text,
  isrc text,
  version text default 'Original',
  status text default 'draft',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_rights (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  track_id uuid,
  right_type text not null default 'master',
  owner_name text not null,
  share_percent numeric(7,4) default 0,
  territory text default 'Worldwide',
  reference text,
  status text default 'pending',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_distributions (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  track_id uuid,
  distributor text not null,
  territories text default 'Worldwide',
  release_date date,
  stores text,
  status text default 'draft',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_promotions (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  track_id uuid,
  campaign_name text not null,
  channel text,
  budget numeric(14,4),
  start_date date,
  end_date date,
  status text default 'draft',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_media_outreach (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  track_id uuid,
  outlet_name text not null,
  outlet_type text default 'Radio',
  contact text,
  submission_url text,
  status text default 'pending',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_live_events (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  event_name text not null,
  venue text,
  event_date date,
  promoter text,
  fee numeric(14,4),
  status text default 'draft',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_fans (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  name text not null,
  email text,
  country text,
  source text default 'KOJA MUSIC',
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_monetisation (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  track_id uuid,
  source text not null,
  period text,
  gross_amount numeric(18,6) default 0,
  currency text default 'USD',
  reference text,
  status text default 'pending',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_royalties (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  track_id uuid,
  payee_name text not null,
  right_type text default 'master',
  share_percent numeric(9,5) default 0,
  gross_amount numeric(18,6) default 0,
  royalty_amount numeric(18,6) default 0,
  period text,
  status text default 'pending',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_music_accounting (
  id uuid primary key default gen_random_uuid(),
  created_by uuid,
  artist_id uuid,
  entry_type text default 'income',
  description text not null,
  amount numeric(18,6) default 0,
  currency text default 'USD',
  reference text,
  entry_date date,
  status text default 'draft',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Indexes for the lifecycle dashboard and release/artist tracing.
create index if not exists koja_music_songwriters_owner_idx on public.koja_music_songwriters(created_by,created_at desc);
create index if not exists koja_music_producers_owner_idx on public.koja_music_producers(created_by,created_at desc);
create index if not exists koja_music_recordings_track_idx on public.koja_music_recordings(track_id,created_at desc);
create index if not exists koja_music_rights_track_idx on public.koja_music_rights(track_id,status,created_at desc);
create index if not exists koja_music_distributions_track_idx on public.koja_music_distributions(track_id,status,created_at desc);
create index if not exists koja_music_promotions_track_idx on public.koja_music_promotions(track_id,status,created_at desc);
create index if not exists koja_music_media_outreach_track_idx on public.koja_music_media_outreach(track_id,status,created_at desc);
create index if not exists koja_music_live_events_artist_idx on public.koja_music_live_events(artist_id,event_date desc);
create index if not exists koja_music_fans_artist_idx on public.koja_music_fans(artist_id,created_at desc);
create index if not exists koja_music_monetisation_track_idx on public.koja_music_monetisation(track_id,period,created_at desc);
create index if not exists koja_music_royalties_track_idx on public.koja_music_royalties(track_id,period,created_at desc);
create index if not exists koja_music_accounting_artist_idx on public.koja_music_accounting(artist_id,entry_date desc,created_at desc);

-- Protect lifecycle tables when they are exposed through Supabase Data API.
-- The KOJA Flask backend uses the server-side Supabase credential for these writes.
alter table public.koja_music_songwriters enable row level security;
alter table public.koja_music_producers enable row level security;
alter table public.koja_music_recordings enable row level security;
alter table public.koja_music_rights enable row level security;
alter table public.koja_music_distributions enable row level security;
alter table public.koja_music_promotions enable row level security;
alter table public.koja_music_media_outreach enable row level security;
alter table public.koja_music_live_events enable row level security;
alter table public.koja_music_fans enable row level security;
alter table public.koja_music_monetisation enable row level security;
alter table public.koja_music_royalties enable row level security;
alter table public.koja_music_accounting enable row level security;

-- Keep Data API access explicit. Service role bypasses RLS; authenticated access
-- is intentionally not opened broadly by this migration.
grant all on table public.koja_music_songwriters to service_role;
grant all on table public.koja_music_producers to service_role;
grant all on table public.koja_music_recordings to service_role;
grant all on table public.koja_music_rights to service_role;
grant all on table public.koja_music_distributions to service_role;
grant all on table public.koja_music_promotions to service_role;
grant all on table public.koja_music_media_outreach to service_role;
grant all on table public.koja_music_live_events to service_role;
grant all on table public.koja_music_fans to service_role;
grant all on table public.koja_music_monetisation to service_role;
grant all on table public.koja_music_royalties to service_role;
grant all on table public.koja_music_accounting to service_role;
