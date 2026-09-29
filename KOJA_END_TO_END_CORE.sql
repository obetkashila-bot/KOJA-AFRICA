-- KOJA End-to-End Core Layer
create extension if not exists pgcrypto;

create table if not exists public.koja_support_tickets (
 id uuid primary key default gen_random_uuid(),
 user_id uuid,
 subject text not null,
 category text not null default 'General',
 priority text not null default 'normal',
 status text not null default 'open',
 message text not null,
 admin_reply text not null default '',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_support_tickets_user_idx on public.koja_support_tickets(user_id,created_at desc);
create index if not exists koja_support_tickets_status_idx on public.koja_support_tickets(status,created_at desc);

create table if not exists public.koja_saved_items (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null,
 item_type text not null,
 item_id text not null,
 title text not null default '',
 url text not null default '',
 created_at timestamptz not null default now(),
 unique(user_id,item_type,item_id)
);
create index if not exists koja_saved_items_user_idx on public.koja_saved_items(user_id,created_at desc);

create table if not exists public.koja_reports (
 id uuid primary key default gen_random_uuid(),
 reporter_id uuid,
 target_type text not null,
 target_id text not null,
 reason text not null,
 details text not null default '',
 status text not null default 'open',
 admin_note text not null default '',
 created_at timestamptz not null default now(),
 resolved_at timestamptz
);
create index if not exists koja_reports_status_idx on public.koja_reports(status,created_at desc);

create table if not exists public.koja_user_preferences (
 user_id uuid primary key,
 language text not null default 'English',
 country text not null default '',
 timezone text not null default 'UTC',
 notifications_enabled boolean not null default true,
 marketing_enabled boolean not null default false,
 updated_at timestamptz not null default now()
);

create table if not exists public.koja_audit_events (
 id uuid primary key default gen_random_uuid(),
 user_id uuid,
 event_type text not null,
 resource_type text not null default '',
 resource_id text not null default '',
 details jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
create index if not exists koja_audit_events_date_idx on public.koja_audit_events(created_at desc);

-- Public storage bucket registry is intentionally not created here because
-- Supabase Storage bucket creation depends on the project's storage policy setup.
