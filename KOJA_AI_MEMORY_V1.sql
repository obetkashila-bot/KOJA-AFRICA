-- KOJA AI Memory V1
-- Additive migration only. Does not drop/recreate existing tables.
create table if not exists public.koja_ai_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  memory text not null,
  category text not null default 'general',
  importance integer not null default 7 check (importance between 1 and 10),
  source text not null default 'explicit',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists koja_ai_memories_user_active_idx
  on public.koja_ai_memories(user_id, is_active, updated_at desc);

create index if not exists koja_ai_memories_user_memory_idx
  on public.koja_ai_memories(user_id, memory);

alter table public.koja_ai_memories enable row level security;

drop policy if exists "Users can read own AI memories" on public.koja_ai_memories;
create policy "Users can read own AI memories"
  on public.koja_ai_memories for select
  using (auth.uid() = user_id);

drop policy if exists "Users can insert own AI memories" on public.koja_ai_memories;
create policy "Users can insert own AI memories"
  on public.koja_ai_memories for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users can update own AI memories" on public.koja_ai_memories;
create policy "Users can update own AI memories"
  on public.koja_ai_memories for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "Users can delete own AI memories" on public.koja_ai_memories;
create policy "Users can delete own AI memories"
  on public.koja_ai_memories for delete
  using (auth.uid() = user_id);
