-- KOJA Communication contact import migration
-- Additive and safe to run once in Supabase SQL Editor.

create table if not exists public.koja_external_contacts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  provider text not null,
  external_id text not null,
  display_name text default '',
  koja_user_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, provider, external_id)
);
create index if not exists koja_external_contacts_user_idx on public.koja_external_contacts(user_id, provider);
create index if not exists koja_external_contacts_external_idx on public.koja_external_contacts(provider, external_id);
create index if not exists koja_external_contacts_koja_user_idx on public.koja_external_contacts(koja_user_id);
