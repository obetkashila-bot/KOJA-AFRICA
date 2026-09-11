-- KOJA AI Memory V2
-- Additive/idempotent migration. Does not drop or recreate existing KOJA tables.
-- Run once in the Supabase SQL Editor.

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
create policy "Users can read own AI memories" on public.koja_ai_memories for select using (auth.uid() = user_id);
drop policy if exists "Users can insert own AI memories" on public.koja_ai_memories;
create policy "Users can insert own AI memories" on public.koja_ai_memories for insert with check (auth.uid() = user_id);
drop policy if exists "Users can update own AI memories" on public.koja_ai_memories;
create policy "Users can update own AI memories" on public.koja_ai_memories for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "Users can delete own AI memories" on public.koja_ai_memories;
create policy "Users can delete own AI memories" on public.koja_ai_memories for delete using (auth.uid() = user_id);

create table if not exists public.koja_ai_file_memory (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  file_name text not null,
  content text not null,
  content_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists koja_ai_file_memory_user_hash_uidx
  on public.koja_ai_file_memory(user_id, content_hash);
create index if not exists koja_ai_file_memory_user_updated_idx
  on public.koja_ai_file_memory(user_id, updated_at desc);

alter table public.koja_ai_file_memory enable row level security;
drop policy if exists "Users can read own AI file memory" on public.koja_ai_file_memory;
create policy "Users can read own AI file memory" on public.koja_ai_file_memory for select using (auth.uid() = user_id);
drop policy if exists "Users can insert own AI file memory" on public.koja_ai_file_memory;
create policy "Users can insert own AI file memory" on public.koja_ai_file_memory for insert with check (auth.uid() = user_id);
drop policy if exists "Users can update own AI file memory" on public.koja_ai_file_memory;
create policy "Users can update own AI file memory" on public.koja_ai_file_memory for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "Users can delete own AI file memory" on public.koja_ai_file_memory;
create policy "Users can delete own AI file memory" on public.koja_ai_file_memory for delete using (auth.uid() = user_id);
