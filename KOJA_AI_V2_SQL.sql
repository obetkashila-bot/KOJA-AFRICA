create table if not exists public.koja_ai_conversations (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 title text not null default 'New KOJA AI chat', is_archived boolean not null default false,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_ai_conversations_user_idx on public.koja_ai_conversations(user_id, updated_at desc);
create table if not exists public.koja_ai_messages (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_ai_conversations(id) on delete cascade,
 user_id uuid not null, role text not null check (role in ('user','assistant')), content text not null,
 created_at timestamptz not null default now()
);
create index if not exists koja_ai_messages_conversation_idx on public.koja_ai_messages(conversation_id, created_at asc);
create index if not exists koja_ai_messages_user_idx on public.koja_ai_messages(user_id, created_at desc);
notify pgrst, 'reload schema';
