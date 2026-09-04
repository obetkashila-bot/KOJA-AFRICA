-- KOJA AFRICA public feed reliability migration
create extension if not exists pgcrypto;
create table if not exists public.koja_public_posts (
 id uuid primary key default gen_random_uuid(),
 author_id uuid not null,
 post_type text not null default 'update',
 title text,
 body text not null,
 media_url text,
 media_type text,
 created_at timestamptz default now(),
 updated_at timestamptz default now(),
 is_published boolean default true
);

create index if not exists koja_public_posts_feed_idx
 on public.koja_public_posts(is_published, created_at desc);
create index if not exists koja_public_posts_author_idx
 on public.koja_public_posts(author_id, created_at desc);

create table if not exists public.koja_public_likes (
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 user_id uuid not null,
 created_at timestamptz default now(),
 primary key(post_id,user_id)
);
create table if not exists public.koja_public_comments (
 id uuid primary key default gen_random_uuid(),
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 author_id uuid not null,
 body text not null,
 created_at timestamptz default now()
);

-- The Flask app uses the Supabase service key, so these grants allow the REST
-- endpoint to work even when a project was created with restrictive defaults.
grant select, insert, update, delete on public.koja_public_posts to service_role;
grant select, insert, update, delete on public.koja_public_likes to service_role;
grant select, insert, update, delete on public.koja_public_comments to service_role;
