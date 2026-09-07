create table if not exists public.koja_news_reactions (post_id uuid not null references public.koja_public_posts(id) on delete cascade,user_id uuid not null,reaction text not null default 'like',created_at timestamptz default now(),primary key(post_id,user_id));
create index if not exists koja_news_reactions_post_idx on public.koja_news_reactions(post_id);
create table if not exists public.koja_media_events (id uuid primary key default gen_random_uuid(),post_id uuid references public.koja_public_posts(id) on delete cascade,user_id uuid,session_id text not null,event_type text not null,watch_seconds numeric default 0,completion_percent numeric default 0,created_at timestamptz default now());
create index if not exists koja_media_events_post_idx on public.koja_media_events(post_id,created_at desc);
create index if not exists koja_media_events_session_idx on public.koja_media_events(session_id,created_at desc);
create table if not exists public.koja_ai_feedback (id uuid primary key default gen_random_uuid(),user_id uuid,rating text,prompt_hash text,created_at timestamptz default now());
