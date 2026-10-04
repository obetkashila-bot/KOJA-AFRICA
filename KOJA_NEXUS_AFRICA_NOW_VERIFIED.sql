-- KOJA NEXUS — AFRICA NOW feed cache
create table if not exists public.koja_nexus_africa_now (
    id uuid primary key default gen_random_uuid(),
    source_key text not null,
    title text not null,
    url text not null,
    source_name text,
    category text,
    country text,
    published_at timestamptz,
    fetched_at timestamptz not null default now(),
    score numeric not null default 0,
    image_url text,
    video_url text,
    media_type text not null default 'story',
    is_live boolean not null default false,
    is_active boolean not null default true,
    summary text,
    created_at timestamptz not null default now()
);
create index if not exists koja_nexus_africa_now_active_score_idx on public.koja_nexus_africa_now (is_active, score desc, published_at desc);
create index if not exists koja_nexus_africa_now_country_idx on public.koja_nexus_africa_now (country);
create index if not exists koja_nexus_africa_now_live_idx on public.koja_nexus_africa_now (is_live, is_active);
