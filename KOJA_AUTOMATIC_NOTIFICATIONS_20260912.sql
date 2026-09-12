-- KOJA Automatic Notifications V1
-- Additive migration only. Does not drop or recreate existing data.

create table if not exists public.koja_notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  notification_type text,
  title text,
  body text,
  related_id uuid,
  is_read boolean default false,
  created_at timestamptz default now()
);

alter table if exists public.koja_notifications add column if not exists notification_type text;
alter table if exists public.koja_notifications add column if not exists title text;
alter table if exists public.koja_notifications add column if not exists body text;
alter table if exists public.koja_notifications add column if not exists related_id uuid;
alter table if exists public.koja_notifications add column if not exists is_read boolean default false;
alter table if exists public.koja_notifications add column if not exists created_at timestamptz default now();
create index if not exists koja_notifications_user_idx on public.koja_notifications(user_id,is_read,created_at desc);

create table if not exists public.koja_notification_preferences (
  user_id uuid primary key,
  push_enabled boolean default true,
  sound_enabled boolean default true,
  market_enabled boolean default true,
  delivery_enabled boolean default true,
  ai_enabled boolean default true,
  messages_enabled boolean default true,
  business_enabled boolean default true,
  calls_enabled boolean default true,
  system_enabled boolean default true,
  updated_at timestamptz default now()
);

alter table if exists public.koja_notification_preferences add column if not exists push_enabled boolean default true;
alter table if exists public.koja_notification_preferences add column if not exists sound_enabled boolean default true;
alter table if exists public.koja_notification_preferences add column if not exists market_enabled boolean default true;
alter table if exists public.koja_notification_preferences add column if not exists delivery_enabled boolean default true;
alter table if exists public.koja_notification_preferences add column if not exists ai_enabled boolean default true;
alter table if exists public.koja_notification_preferences add column if not exists messages_enabled boolean default true;
alter table if exists public.koja_notification_preferences add column if not exists business_enabled boolean default true;
alter table if exists public.koja_notification_preferences add column if not exists calls_enabled boolean default true;
alter table if exists public.koja_notification_preferences add column if not exists system_enabled boolean default true;
alter table if exists public.koja_notification_preferences add column if not exists updated_at timestamptz default now();

create table if not exists public.koja_push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  endpoint text not null,
  subscription jsonb not null default '{}'::jsonb,
  user_agent text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique(user_id,endpoint)
);
alter table if exists public.koja_push_subscriptions add column if not exists user_id uuid;
alter table if exists public.koja_push_subscriptions add column if not exists endpoint text;
alter table if exists public.koja_push_subscriptions add column if not exists subscription jsonb not null default '{}'::jsonb;
alter table if exists public.koja_push_subscriptions add column if not exists user_agent text;
alter table if exists public.koja_push_subscriptions add column if not exists created_at timestamptz default now();
alter table if exists public.koja_push_subscriptions add column if not exists updated_at timestamptz default now();
create index if not exists koja_push_subscriptions_user_idx on public.koja_push_subscriptions(user_id,created_at desc);

-- Verification
select column_name, data_type
from information_schema.columns
where table_schema='public'
  and table_name in ('koja_notifications','koja_notification_preferences','koja_push_subscriptions')
order by table_name, ordinal_position;
