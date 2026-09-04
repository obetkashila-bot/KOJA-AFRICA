-- KOJA AFRICA: Large-class SFU + moderation + attendance
alter table if exists public.teacher_live_rooms add column if not exists livekit_room_name text;
alter table if exists public.teacher_live_rooms add column if not exists classroom_mode text default 'large_sfu';
alter table if exists public.teacher_live_rooms add column if not exists max_participants integer default 500;
alter table if exists public.teacher_live_rooms add column if not exists started_at timestamptz;
alter table if exists public.teacher_live_rooms add column if not exists ended_at timestamptz;
create index if not exists teacher_live_rooms_livekit_idx on public.teacher_live_rooms(livekit_room_name);
update public.teacher_live_rooms set classroom_mode='large_sfu', max_participants=coalesce(max_participants,500) where classroom_mode is null or classroom_mode='';
update public.teacher_live_rooms set livekit_room_name='koja-class-'||id where livekit_room_name is null;

create table if not exists public.teacher_live_attendance (
 id uuid primary key default gen_random_uuid(),
 room_id uuid not null references public.teacher_live_rooms(id) on delete cascade,
 user_id uuid not null,
 identity text not null,
 display_name text,
 joined_at timestamptz default now(),
 left_at timestamptz,
 created_at timestamptz default now()
);
create index if not exists teacher_live_attendance_room_idx on public.teacher_live_attendance(room_id, joined_at desc);
create index if not exists teacher_live_attendance_user_idx on public.teacher_live_attendance(user_id, joined_at desc);
