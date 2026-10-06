-- KOJA MUSIC — core schema (run once in Supabase SQL editor)
-- Covers: artist profiles, tracks, likes, plays + the public storage bucket.
-- The server uses the service key, so RLS is not required for these tables.

create table if not exists koja_music_artists (
  id           uuid primary key,
  created_by   uuid,
  artist_name  text not null,
  country      text,
  genre        text,
  bio          text,
  status       text not null default 'pending',   -- pending | published | approved | active | suspended
  active       boolean not null default false,
  featured     boolean not null default false,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists koja_music_artists_created_by_idx on koja_music_artists (created_by);
create index if not exists koja_music_artists_status_idx     on koja_music_artists (status);

create table if not exists koja_music_tracks (
  id                    uuid primary key,
  artist_id             uuid references koja_music_artists(id) on delete cascade,
  title                 text not null,
  release_type          text default 'single',
  album_title           text,
  genre                 text,
  description           text,
  video_url             text,
  music_video_url       text,
  visual_url            text,
  audio_url             text,
  stream_url            text,
  cover_image_url       text,
  external_video_url    text,
  external_video_provider text,
  master_owner          text,
  composition_owner     text,
  licence_reference     text,
  downloadable_visual   boolean not null default false,
  downloadable_audio    boolean not null default false,
  status                text not null default 'pending',  -- pending | published | rejected | suspended
  rights_status         text default 'pending',           -- pending | verified | external_embed
  featured              boolean not null default false,
  release_date          date,
  created_by            uuid,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create index if not exists koja_music_tracks_artist_idx on koja_music_tracks (artist_id);
create index if not exists koja_music_tracks_status_idx on koja_music_tracks (status, featured, release_date desc);

-- track_id/user_id are text so external catalogue ids (e.g. 'ext-...') also work
create table if not exists koja_music_likes (
  id         uuid primary key,
  user_id    text not null,
  track_id   text not null,
  created_at timestamptz not null default now(),
  unique (user_id, track_id)
);
create index if not exists koja_music_likes_track_idx on koja_music_likes (track_id);

create table if not exists koja_music_plays (
  id          uuid primary key,
  track_id    text not null,
  user_id     text,
  session_key text,
  created_at  timestamptz not null default now()
);
create index if not exists koja_music_plays_track_idx on koja_music_plays (track_id);

-- Public bucket for videos/audio/artwork (matches SUPABASE_STORAGE_BUCKET default).
-- file_size_limit must be >= KOJA_MUSIC_MAX_MB (100 MB here). Supabase's free
-- plan caps a single file at 50 MB: raise it in Storage settings on a paid plan.
insert into storage.buckets (id, name, public, file_size_limit)
values ('koja-files', 'koja-files', true, 104857600)
on conflict (id) do update set public = true, file_size_limit = 104857600;
