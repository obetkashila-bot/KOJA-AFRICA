-- KOJA Research Books V2
-- Additive/update-safe migration. Does not recreate or delete existing tables.

create table if not exists public.koja_research_books (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    source text not null default '',
    external_id text not null default '',
    title text not null,
    authors jsonb not null default '[]'::jsonb,
    year integer,
    publisher text default '',
    isbn text default '',
    landing_url text default '',
    preview_url text default '',
    download_url text default '',
    download_format text default '',
    access text default 'metadata',
    cover_url text default '',
    language text default '',
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists koja_research_books_user_idx
    on public.koja_research_books(user_id, created_at desc);

create index if not exists koja_research_books_source_idx
    on public.koja_research_books(source, external_id);

create unique index if not exists koja_research_books_user_source_external_uidx
    on public.koja_research_books(user_id, source, external_id)
    where external_id <> '';
