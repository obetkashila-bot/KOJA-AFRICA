-- KOJA AI CORE V1
-- Additive/idempotent migration. Does not drop or recreate existing KOJA AI tables.

create extension if not exists pgcrypto;

create table if not exists public.koja_ai_core_knowledge (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  content text not null,
  source text default 'koja-core',
  is_verified boolean not null default false,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.koja_ai_core_learnings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  learning text not null,
  source text default 'user',
  is_verified boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.koja_ai_core_tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  task_type text not null,
  prompt text,
  result text,
  provider text,
  status text default 'ok',
  metadata text default '{}',
  created_at timestamptz not null default now()
);

create table if not exists public.koja_ai_provider_health (
  id uuid primary key default gen_random_uuid(),
  provider text unique not null,
  status text default 'unknown',
  failure_count integer not null default 0,
  last_error text default '',
  last_checked_at timestamptz,
  last_success_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.koja_ai_evaluations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  task_id uuid references public.koja_ai_core_tasks(id) on delete set null,
  score numeric,
  feedback text,
  is_verified boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_koja_ai_core_knowledge_active on public.koja_ai_core_knowledge(is_active, updated_at desc);
create index if not exists idx_koja_ai_core_learnings_user on public.koja_ai_core_learnings(user_id, created_at desc);
create index if not exists idx_koja_ai_core_tasks_user on public.koja_ai_core_tasks(user_id, created_at desc);
create index if not exists idx_koja_ai_evaluations_user on public.koja_ai_evaluations(user_id, created_at desc);

alter table public.koja_ai_core_knowledge enable row level security;
alter table public.koja_ai_core_learnings enable row level security;
alter table public.koja_ai_core_tasks enable row level security;
alter table public.koja_ai_provider_health enable row level security;
alter table public.koja_ai_evaluations enable row level security;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_knowledge' and policyname='koja_core_knowledge_select') then
    create policy koja_core_knowledge_select on public.koja_ai_core_knowledge for select to authenticated using (is_active = true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_learnings' and policyname='koja_core_learnings_owner') then
    create policy koja_core_learnings_owner on public.koja_ai_core_learnings for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_tasks' and policyname='koja_core_tasks_owner') then
    create policy koja_core_tasks_owner on public.koja_ai_core_tasks for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_provider_health' and policyname='koja_core_provider_health_select') then
    create policy koja_core_provider_health_select on public.koja_ai_provider_health for select to authenticated using (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_evaluations' and policyname='koja_core_evaluations_owner') then
    create policy koja_core_evaluations_owner on public.koja_ai_evaluations for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
end $$;

-- Optional starter knowledge can be inserted later after deployment.
