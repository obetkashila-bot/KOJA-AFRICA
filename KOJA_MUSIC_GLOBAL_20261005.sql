-- KOJA MUSIC GLOBAL — additive production migration
-- Extends the existing KOJA MUSIC schema without deleting existing data.
-- Fixes the historical featured-column error by adding compatibility columns first.
-- No artificial business/catalogue limit is imposed.

create extension if not exists pgcrypto;

-- ============================================================
-- Existing compatibility columns
-- ============================================================
alter table if exists public.koja_music_artists add column if not exists featured boolean default false;
alter table if exists public.koja_music_artists add column if not exists genre text;
alter table if exists public.koja_music_artists add column if not exists genres text;
alter table if exists public.koja_music_artists add column if not exists bio text;
alter table if exists public.koja_music_artists add column if not exists profile_image_url text;
alter table if exists public.koja_music_artists add column if not exists rights_status text default 'review_required';
alter table if exists public.koja_music_artists add column if not exists reviewed_by text;
alter table if exists public.koja_music_artists add column if not exists reviewed_at timestamptz;
alter table if exists public.koja_music_artists add column if not exists updated_at timestamptz default now();

alter table if exists public.koja_music_tracks add column if not exists featured boolean default false;
alter table if exists public.koja_music_tracks add column if not exists release_id uuid;
alter table if exists public.koja_music_tracks add column if not exists plays bigint default 0;
alter table if exists public.koja_music_tracks add column if not exists last_played_at timestamptz;
alter table if exists public.koja_music_tracks add column if not exists reviewed_by text;
alter table if exists public.koja_music_tracks add column if not exists reviewed_at timestamptz;
alter table if exists public.koja_music_tracks add column if not exists published_at timestamptz;

-- ============================================================
-- Global release catalogue: singles, EPs and albums
-- ============================================================
create table if not exists public.koja_music_releases (
    id uuid primary key default gen_random_uuid(),
    artist_id uuid,
    title text not null,
    slug text,
    release_type text not null default 'single',
    description text,
    genre text,
    country text,
    cover_art_url text,
    cover_art_path text,
    release_date date,
    status text not null default 'draft',
    featured boolean not null default false,
    created_by text,
    reviewed_by text,
    reviewed_at timestamptz,
    published_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.koja_music_releases add column if not exists release_type text default 'single';
alter table public.koja_music_releases add column if not exists featured boolean default false;
alter table public.koja_music_releases add column if not exists cover_art_path text;
alter table public.koja_music_releases add column if not exists country text;
alter table public.koja_music_releases add column if not exists status text default 'draft';

-- ============================================================
-- Rights / licensing ledger
-- ============================================================
create table if not exists public.koja_music_rights (
    id uuid primary key default gen_random_uuid(),
    artist_id uuid,
    release_id uuid,
    track_id uuid,
    master_owner text,
    composition_owner text,
    publishing_owner text,
    licence_type text,
    licence_reference text,
    licence_document_url text,
    territory text not null default 'global',
    starts_at timestamptz,
    expires_at timestamptz,
    rights_status text not null default 'pending',
    verified_by text,
    verified_at timestamptz,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- ============================================================
-- Artist/release submission workflow
-- ============================================================
create table if not exists public.koja_music_artist_submissions (
    id uuid primary key default gen_random_uuid()
);
alter table public.koja_music_artist_submissions add column if not exists user_id uuid;
alter table public.koja_music_artist_submissions add column if not exists artist_name text;
alter table public.koja_music_artist_submissions add column if not exists country text;
alter table public.koja_music_artist_submissions add column if not exists genre text;
alter table public.koja_music_artist_submissions add column if not exists website text;
alter table public.koja_music_artist_submissions add column if not exists bio text;
alter table public.koja_music_artist_submissions add column if not exists catalogue_links text;
alter table public.koja_music_artist_submissions add column if not exists rights_declaration boolean default false;
alter table public.koja_music_artist_submissions add column if not exists status text default 'pending';
alter table public.koja_music_artist_submissions add column if not exists reviewer_id uuid;
alter table public.koja_music_artist_submissions add column if not exists reviewer_notes text;
alter table public.koja_music_artist_submissions add column if not exists created_at timestamptz default now();
alter table public.koja_music_artist_submissions add column if not exists updated_at timestamptz default now();

-- ============================================================
-- Playlists
-- ============================================================
create table if not exists public.koja_music_playlists (
    id uuid primary key default gen_random_uuid(),
    owner_user_id uuid,
    name text not null,
    description text,
    cover_url text,
    visibility text not null default 'public',
    featured boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.koja_music_playlist_tracks (
    playlist_id uuid not null references public.koja_music_playlists(id) on delete cascade,
    track_id uuid not null references public.koja_music_tracks(id) on delete cascade,
    position integer not null default 0,
    added_at timestamptz not null default now(),
    primary key (playlist_id, track_id)
);

-- ============================================================
-- Play analytics
-- ============================================================
create table if not exists public.koja_music_plays (
    id uuid primary key default gen_random_uuid()
);
alter table public.koja_music_plays add column if not exists track_id uuid;
alter table public.koja_music_plays add column if not exists user_id uuid;
alter table public.koja_music_plays add column if not exists session_id text;
alter table public.koja_music_plays add column if not exists country text;
alter table public.koja_music_plays add column if not exists device_type text;
alter table public.koja_music_plays add column if not exists source text;
alter table public.koja_music_plays add column if not exists played_at timestamptz default now();

-- ============================================================
-- Recruitment remains separate from licensing/catalogue.
-- Existing WhatsApp recruitment is untouched.
-- ============================================================
create table if not exists public.koja_music_recruitment_targets (
    id uuid primary key default gen_random_uuid(),
    artist_name text not null,
    country text not null,
    source_url text,
    public_contact text,
    genre text,
    priority integer not null default 2,
    status text not null default 'not_contacted',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (artist_name, country)
);

-- ============================================================
-- Indexes: created only after compatibility columns exist.
-- ============================================================
create index if not exists idx_km_artist_status_featured on public.koja_music_artists(status, featured desc, created_at desc);
create index if not exists idx_km_artist_country on public.koja_music_artists(country);
create index if not exists idx_km_artist_genre on public.koja_music_artists(genre);
create index if not exists idx_km_track_status_featured on public.koja_music_tracks(status, featured desc, created_at desc);
create index if not exists idx_km_track_artist on public.koja_music_tracks(artist_id, status);
create index if not exists idx_km_track_release on public.koja_music_tracks(release_id, created_at desc);
create index if not exists idx_km_track_genre on public.koja_music_tracks(genre);
create index if not exists idx_km_rights_status on public.koja_music_rights(rights_status, expires_at);
create index if not exists idx_km_submission_status on public.koja_music_artist_submissions(status, created_at desc);
create index if not exists idx_km_play_track_time on public.koja_music_plays(track_id, played_at desc);
create index if not exists idx_km_recruitment_country on public.koja_music_recruitment_targets(country, priority, status);

-- ============================================================
-- Timestamp trigger
-- ============================================================
create or replace function public.koja_music_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_km_artist_updated on public.koja_music_artists;
create trigger trg_km_artist_updated before update on public.koja_music_artists
for each row execute function public.koja_music_updated_at();

drop trigger if exists trg_km_track_updated on public.koja_music_tracks;
create trigger trg_km_track_updated before update on public.koja_music_tracks
for each row execute function public.koja_music_updated_at();

drop trigger if exists trg_km_release_updated on public.koja_music_releases;
create trigger trg_km_release_updated before update on public.koja_music_releases
for each row execute function public.koja_music_updated_at();

drop trigger if exists trg_km_rights_updated on public.koja_music_rights;
create trigger trg_km_rights_updated before update on public.koja_music_rights
for each row execute function public.koja_music_updated_at();

drop trigger if exists trg_km_submission_updated on public.koja_music_artist_submissions;
create trigger trg_km_submission_updated before update on public.koja_music_artist_submissions
for each row execute function public.koja_music_updated_at();

-- Public discovery is deliberately restricted to approved artists and published,
-- rights-approved tracks. Recruitment does not equal streaming permission.
alter table public.koja_music_artists enable row level security;
alter table public.koja_music_tracks enable row level security;
alter table public.koja_music_releases enable row level security;

drop policy if exists "koja_music_public_artists" on public.koja_music_artists;
create policy "koja_music_public_artists" on public.koja_music_artists
for select using (status = 'approved');

drop policy if exists "koja_music_public_tracks" on public.koja_music_tracks;
create policy "koja_music_public_tracks" on public.koja_music_tracks
for select using (status = 'published' and rights_status = 'approved');

drop policy if exists "koja_music_public_releases" on public.koja_music_releases;
create policy "koja_music_public_releases" on public.koja_music_releases
for select using (status = 'published');

-- Existing WhatsApp recruitment tables and records are not modified.
-- Run this migration after KOJA_MUSIC.sql / KOJA_MUSIC_20261005_ADDON_FIXED.sql.
