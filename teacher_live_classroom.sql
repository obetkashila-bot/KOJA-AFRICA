create extension if not exists pgcrypto;

create table if not exists public.teacher_live_rooms (
 id uuid primary key default gen_random_uuid(),
 class_id uuid,
 teacher_id uuid not null,
 provider_id uuid,
 room_code text unique not null,
 title text not null,
 status text default 'live',
 created_at timestamptz default now(),
 ended_at timestamptz
);
create index if not exists teacher_live_rooms_teacher_idx on public.teacher_live_rooms(teacher_id, created_at desc);
create index if not exists teacher_live_rooms_class_idx on public.teacher_live_rooms(class_id, created_at desc);

create table if not exists public.teacher_live_presence (
 room_id uuid not null references public.teacher_live_rooms(id) on delete cascade,
 peer_id text not null,
 user_id uuid not null,
 display_name text,
 is_teacher boolean default false,
 last_seen timestamptz default now(),
 primary key(room_id, peer_id)
);
create index if not exists teacher_live_presence_room_idx on public.teacher_live_presence(room_id, last_seen desc);

create table if not exists public.teacher_live_signals (
 id uuid primary key default gen_random_uuid(),
 room_id uuid not null references public.teacher_live_rooms(id) on delete cascade,
 sender_peer_id text not null,
 recipient_peer_id text,
 signal_type text not null,
 payload jsonb not null,
 created_at timestamptz default now()
);
create index if not exists teacher_live_signals_room_idx on public.teacher_live_signals(room_id, created_at asc);

create table if not exists public.teacher_live_messages (
 id uuid primary key default gen_random_uuid(),
 room_id uuid not null references public.teacher_live_rooms(id) on delete cascade,
 sender_peer_id text not null,
 sender_name text,
 body text not null,
 created_at timestamptz default now()
);
create index if not exists teacher_live_messages_room_idx on public.teacher_live_messages(room_id, created_at asc);

grant select, insert, update, delete on public.teacher_live_rooms to service_role;
grant select, insert, update, delete on public.teacher_live_presence to service_role;
grant select, insert, update, delete on public.teacher_live_signals to service_role;
grant select, insert, update, delete on public.teacher_live_messages to service_role;
