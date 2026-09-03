-- KOJA AFRICA Calling V2 (standalone repair/upgrade SQL)
create extension if not exists pgcrypto;

create table if not exists public.koja_conversations (
 id uuid primary key default gen_random_uuid(), conversation_type text not null default 'direct', created_by uuid,
 name text, avatar_url text, created_at timestamptz default now(), updated_at timestamptz default now()
);

create table if not exists public.koja_conversation_members (
 conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 user_id uuid not null, role text not null default 'member', joined_at timestamptz default now(),
 last_read_at timestamptz, muted boolean default false, primary key(conversation_id,user_id)
);
create index if not exists koja_members_user_idx on public.koja_conversation_members(user_id,conversation_id);

create table if not exists public.koja_calls (
 id uuid primary key default gen_random_uuid(),
 conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 caller_id uuid not null, callee_id uuid not null,
 mode text not null default 'video', status text not null default 'ringing',
 offer text, answer text,
 caller_ice jsonb default '[]'::jsonb,
 callee_ice jsonb default '[]'::jsonb,
 created_at timestamptz default now(), answered_at timestamptz, ended_at timestamptz
);
alter table public.koja_calls add column if not exists caller_ice jsonb default '[]'::jsonb;
alter table public.koja_calls add column if not exists callee_ice jsonb default '[]'::jsonb;
create index if not exists koja_calls_callee_idx on public.koja_calls(callee_id,status,created_at desc);
create index if not exists koja_calls_caller_idx on public.koja_calls(caller_id,status,created_at desc);

create table if not exists public.koja_push_tokens (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null,
 token text not null unique,
 platform text not null default 'android',
 device_name text,
 enabled boolean not null default true,
 created_at timestamptz default now(),
 updated_at timestamptz default now(),
 last_seen_at timestamptz default now()
);
create index if not exists koja_push_tokens_user_idx on public.koja_push_tokens(user_id,enabled,updated_at desc);
create index if not exists koja_push_tokens_token_idx on public.koja_push_tokens(token);

create table if not exists public.koja_notifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, notification_type text,
 title text, body text, related_id uuid, is_read boolean default false, created_at timestamptz default now()
);
create index if not exists koja_notifications_user_idx on public.koja_notifications(user_id,is_read,created_at desc);
