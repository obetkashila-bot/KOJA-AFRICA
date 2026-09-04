-- KOJA AFRICA: scalable large-classroom migration
-- Media is handled by LiveKit SFU. No peer-to-peer mesh is used for large classes.
alter table if exists public.teacher_live_rooms add column if not exists livekit_room_name text;
alter table if exists public.teacher_live_rooms add column if not exists classroom_mode text default 'large_sfu';
alter table if exists public.teacher_live_rooms add column if not exists max_participants integer default 500;
alter table if exists public.teacher_live_rooms add column if not exists started_at timestamptz;
create index if not exists teacher_live_rooms_livekit_idx on public.teacher_live_rooms(livekit_room_name);
update public.teacher_live_rooms set classroom_mode='large_sfu', max_participants=coalesce(max_participants,500) where classroom_mode is null or classroom_mode='';
