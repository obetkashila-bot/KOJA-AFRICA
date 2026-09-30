-- KOJA AFRICA Terms & Conditions acceptance
-- Run once in Supabase SQL Editor.
create table if not exists public.koja_terms_acceptances (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  terms_version text not null,
  accepted boolean not null default false,
  accepted_at timestamptz null,
  created_at timestamptz not null default now()
);

create index if not exists koja_terms_acceptances_user_version_idx
  on public.koja_terms_acceptances (user_id, terms_version, created_at desc);

create index if not exists koja_terms_acceptances_user_idx
  on public.koja_terms_acceptances (user_id, created_at desc);
