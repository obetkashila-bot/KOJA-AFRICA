-- KOJA AFRICA production migration: settings, notifications and admin username
-- Run in Supabase SQL Editor.

create table if not exists public.user_settings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  theme text not null default 'system' check (theme in ('system','light','dark')),
  language text not null default 'en' check (language in ('en','bem','ny')),
  notify_assignments boolean not null default true,
  notify_delivery boolean not null default true,
  notify_help boolean not null default true,
  notify_announcements boolean not null default false,
  allow_location boolean not null default true,
  allow_research boolean not null default true,
  allow_device_storage boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id)
);

create index if not exists user_settings_user_id_idx on public.user_settings(user_id);

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  title text not null,
  message text not null,
  category text not null default 'general',
  link text,
  is_read boolean not null default false,
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists notifications_user_created_idx on public.notifications(user_id, created_at desc);
create index if not exists notifications_user_unread_idx on public.notifications(user_id, is_read);

create table if not exists public.activity_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  action text not null,
  description text default '',
  created_at timestamptz not null default now()
);

create index if not exists activity_logs_user_created_idx on public.activity_logs(user_id, created_at desc);

-- Add username only if your profiles table does not already have it.
alter table public.profiles add column if not exists username text;
alter table public.profiles add column if not exists is_admin boolean default false;
alter table public.profiles add column if not exists is_active boolean default true;
create unique index if not exists profiles_username_unique_idx on public.profiles(lower(username)) where username is not null and username <> '';

-- Optional: set your administrator username after confirming the email.
-- update public.profiles set username='admin' where lower(email)=lower('YOUR_ADMIN_EMAIL');

-- Useful notification examples are inserted by the Flask application; no service
-- account secrets are stored in this migration.
