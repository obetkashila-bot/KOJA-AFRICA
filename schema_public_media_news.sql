-- KOJA AFRICA Public Communication + News + Media schema
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
create index if not exists koja_public_likes_post_idx
 on public.koja_public_likes(post_id);

create table if not exists public.koja_public_comments (
 id uuid primary key default gen_random_uuid(),
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 author_id uuid not null,
 body text not null,
 created_at timestamptz default now()
);
create index if not exists koja_public_comments_post_idx
 on public.koja_public_comments(post_id,created_at);

create table if not exists public.professional_public_messages (
 id uuid primary key default gen_random_uuid(),
 profession text not null,
 sender_id uuid not null,
 message text not null,
 created_at timestamptz default now(),
 deleted_at timestamptz
);
create index if not exists professional_public_messages_profession_idx
 on public.professional_public_messages(profession, created_at desc);

create table if not exists public.professional_public_posts (
 id uuid primary key default gen_random_uuid(),
 profession text not null,
 author_id uuid not null,
 provider_id uuid,
 title text not null,
 body text not null,
 media_url text,
 created_at timestamptz default now(),
 updated_at timestamptz default now()
);
create index if not exists professional_public_posts_profession_idx
 on public.professional_public_posts(profession, created_at desc);

create table if not exists public.professional_public_comments (
 id uuid primary key default gen_random_uuid(),
 post_id uuid not null references public.professional_public_posts(id) on delete cascade,
 author_id uuid not null,
 body text not null,
 created_at timestamptz default now()
);
create index if not exists professional_public_comments_post_idx
 on public.professional_public_comments(post_id, created_at);
