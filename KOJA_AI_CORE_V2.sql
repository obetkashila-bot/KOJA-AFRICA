-- KOJA AI CORE V2
-- Additive/idempotent migration. Run after KOJA_AI_MEMORY_V2.sql and CORE_V1.sql.
create extension if not exists pgcrypto;

create table if not exists public.koja_ai_core_graph (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  entity text not null,
  entity_type text not null default 'concept',
  relation text not null,
  target text not null,
  source text default 'koja-core',
  confidence numeric default 0.5,
  is_verified boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_koja_ai_core_graph_user on public.koja_ai_core_graph(user_id, updated_at desc);
create index if not exists idx_koja_ai_core_graph_entity on public.koja_ai_core_graph(entity, target);

alter table public.koja_ai_provider_health add column if not exists cooldown_until timestamptz;

create table if not exists public.koja_ai_core_tools (
  id uuid primary key default gen_random_uuid(),
  name text unique not null,
  description text not null,
  tool_type text not null default 'deterministic',
  recipe text default '',
  is_active boolean not null default true,
  is_verified boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.koja_ai_core_proposals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  proposal text not null,
  reason text default '',
  proposed_change text default '',
  status text not null default 'proposed',
  created_at timestamptz not null default now(),
  reviewed_at timestamptz
);

create index if not exists idx_koja_ai_core_proposals_user on public.koja_ai_core_proposals(user_id, created_at desc);

alter table public.koja_ai_core_graph enable row level security;
alter table public.koja_ai_core_tools enable row level security;
alter table public.koja_ai_core_proposals enable row level security;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_select_own') then
    create policy koja_core_graph_select_own on public.koja_ai_core_graph for select using (auth.uid() = user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_insert_own') then
    create policy koja_core_graph_insert_own on public.koja_ai_core_graph for insert with check (auth.uid() = user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_update_own') then
    create policy koja_core_graph_update_own on public.koja_ai_core_graph for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_delete_own') then
    create policy koja_core_graph_delete_own on public.koja_ai_core_graph for delete using (auth.uid() = user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_tools' and policyname='koja_core_tools_select') then
    create policy koja_core_tools_select on public.koja_ai_core_tools for select using (is_active = true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_proposals' and policyname='koja_core_proposals_select_own') then
    create policy koja_core_proposals_select_own on public.koja_ai_core_proposals for select using (auth.uid() = user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_proposals' and policyname='koja_core_proposals_insert_own') then
    create policy koja_core_proposals_insert_own on public.koja_ai_core_proposals for insert with check (auth.uid() = user_id);
  end if;
end $$;

insert into public.koja_ai_core_tools(name,description,tool_type,recipe,is_active,is_verified)
values
 ('calculator','Safe arithmetic and percentage calculations without executing arbitrary code.','deterministic','restricted_ast_arithmetic',true,true),
 ('word_count','Count words in explicitly supplied text.','deterministic','split_whitespace',true,true),
 ('retrieval','Retrieve signed-in user memory, previous conversations and stored file text.','retrieval','core_v2_semantic_retrieval',true,true)
on conflict (name) do update set description=excluded.description, recipe=excluded.recipe, updated_at=now();
