-- KOJA CONNECT V10: additive only
create table if not exists public.koja_fcm_devices (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, token text not null,
 device_id text default '', platform text default 'android', app_version text default '',
 created_at timestamptz default now(), updated_at timestamptz default now(), unique(user_id,token)
);
create index if not exists koja_fcm_devices_user_idx on public.koja_fcm_devices(user_id,updated_at desc);
