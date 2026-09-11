-- KOJA Notification Center V2: Email + SMS channels
-- SAFE / ADDITIVE: no drops, truncates, or table recreation.
create table if not exists public.koja_notification_preferences (
 user_id uuid primary key,
 push_enabled boolean default true,
 email_enabled boolean default true,
 sms_enabled boolean default true,
 sound_enabled boolean default true,
 market_enabled boolean default true,
 delivery_enabled boolean default true,
 ai_enabled boolean default true,
 messages_enabled boolean default true,
 system_enabled boolean default true,
 updated_at timestamptz default now()
);
alter table public.koja_notification_preferences add column if not exists email_enabled boolean default true;
alter table public.koja_notification_preferences add column if not exists sms_enabled boolean default true;
alter table public.profiles add column if not exists phone text;
alter table public.profiles add column if not exists email text;
create index if not exists koja_profiles_phone_idx on public.profiles(phone);
