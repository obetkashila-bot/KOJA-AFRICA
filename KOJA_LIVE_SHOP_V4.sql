-- KOJA LIVE SHOP V4
-- Additive migration: persistent LIVE likes and comments.
-- Does not recreate or delete existing KOJA tables.

create extension if not exists pgcrypto;

create table if not exists public.koja_market_live_likes (
    live_id text not null references public.koja_market_live_rooms(id) on delete cascade,
    user_id uuid not null,
    created_at timestamptz not null default now(),
    primary key (live_id, user_id)
);

create index if not exists koja_market_live_likes_live_idx
    on public.koja_market_live_likes(live_id, created_at desc);

create table if not exists public.koja_market_live_comments (
    id uuid primary key default gen_random_uuid(),
    live_id text not null references public.koja_market_live_rooms(id) on delete cascade,
    user_id uuid not null,
    body text not null check (char_length(body) between 1 and 1000),
    is_hidden boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists koja_market_live_comments_live_idx
    on public.koja_market_live_comments(live_id, created_at asc);
