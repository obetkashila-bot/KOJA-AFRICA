-- KOJA Next-Generation Feed / Media Engine
create extension if not exists pgcrypto;
create table if not exists public.koja_public_posts (
 id uuid primary key default gen_random_uuid(), author_id uuid not null,
 post_type text not null default 'update', title text, body text not null,
 media_url text, media_type text, created_at timestamptz default now(),
 updated_at timestamptz default now(), is_published boolean default true
);
alter table public.koja_public_posts add column if not exists view_count bigint default 0;
alter table public.koja_public_posts add column if not exists share_count bigint default 0;
alter table public.koja_public_posts add column if not exists media_duration numeric;
create index if not exists koja_public_posts_feed_idx on public.koja_public_posts(is_published, created_at desc);
create index if not exists koja_public_posts_author_idx on public.koja_public_posts(author_id, created_at desc);
create table if not exists public.koja_public_likes (
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 user_id uuid not null, created_at timestamptz default now(), primary key(post_id,user_id)
);
create index if not exists koja_public_likes_post_idx on public.koja_public_likes(post_id);
create table if not exists public.koja_public_comments (
 id uuid primary key default gen_random_uuid(), post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 author_id uuid not null, body text not null, created_at timestamptz default now()
);
create index if not exists koja_public_comments_post_idx on public.koja_public_comments(post_id,created_at);
create table if not exists public.koja_feed_events (
 id uuid primary key default gen_random_uuid(), post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 user_id uuid, session_id text, event_type text not null, watch_seconds numeric default 0,
 completion_percent numeric default 0, created_at timestamptz default now()
);
create index if not exists koja_feed_events_post_idx on public.koja_feed_events(post_id,created_at desc);
create index if not exists koja_feed_events_session_idx on public.koja_feed_events(session_id,post_id,event_type);
