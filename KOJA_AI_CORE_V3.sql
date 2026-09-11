create extension if not exists pgcrypto;

-- KOJA AI CORE V3: additive only. Does not drop or recreate existing KOJA tables.
-- V3 uses dependency-free semantic fingerprints in Python, so no embedding API is required.

create table if not exists public.koja_ai_core_graph (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  entity text not null,
  entity_type text not null default 'concept',
  relation text not null,
  target text not null,
  source text default 'core',
  confidence numeric default 0.5,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_koja_ai_core_graph_user on public.koja_ai_core_graph(user_id, updated_at desc);
create index if not exists idx_koja_ai_core_graph_entity on public.koja_ai_core_graph(entity, target);

alter table public.koja_ai_core_graph enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_select_own') then
    create policy koja_core_graph_select_own on public.koja_ai_core_graph for select using (auth.uid()=user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_insert_own') then
    create policy koja_core_graph_insert_own on public.koja_ai_core_graph for insert with check (auth.uid()=user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_update_own') then
    create policy koja_core_graph_update_own on public.koja_ai_core_graph for update using (auth.uid()=user_id) with check (auth.uid()=user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_delete_own') then
    create policy koja_core_graph_delete_own on public.koja_ai_core_graph for delete using (auth.uid()=user_id);
  end if;
end $$;

-- Add circuit-breaker fields to the existing provider-health table without replacing it.
alter table public.koja_ai_provider_health add column if not exists cooldown_until timestamptz;
alter table public.koja_ai_provider_health add column if not exists total_requests integer not null default 0;
alter table public.koja_ai_provider_health add column if not exists total_failures integer not null default 0;

-- Optional semantic cache for future vector/embedding providers. V3 itself does not require it.
create table if not exists public.koja_ai_core_semantic_cache (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  query_text text not null,
  result jsonb not null default '[]'::jsonb,
  engine text not null default 'core-v3-hash',
  created_at timestamptz not null default now(),
  expires_at timestamptz
);
create index if not exists idx_koja_ai_core_semantic_cache_user on public.koja_ai_core_semantic_cache(user_id, created_at desc);
alter table public.koja_ai_core_semantic_cache enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_semantic_cache' and policyname='koja_core_cache_select_own') then
    create policy koja_core_cache_select_own on public.koja_ai_core_semantic_cache for select using (auth.uid()=user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_semantic_cache' and policyname='koja_core_cache_insert_own') then
    create policy koja_core_cache_insert_own on public.koja_ai_core_semantic_cache for insert with check (auth.uid()=user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_semantic_cache' and policyname='koja_core_cache_delete_own') then
    create policy koja_core_cache_delete_own on public.koja_ai_core_semantic_cache for delete using (auth.uid()=user_id);
  end if;
end $$;
