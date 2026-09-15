-- KOJA IDENTITY & TRUST V2
-- Additive/update-safe. No existing table is dropped or recreated.
create table if not exists public.koja_identity_v2_verifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  organization_id uuid null,
  legal_name text not null default '',
  country text not null default 'ZM',
  document_type text not null default 'other',
  document_hash text not null default '',
  status text not null default 'pending',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_kit2_verifications_status on public.koja_identity_v2_verifications(status, updated_at desc);

create table if not exists public.koja_identity_v2_devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  organization_id uuid null,
  fingerprint_hash text not null,
  platform text not null default '',
  user_agent text not null default '',
  trusted boolean not null default false,
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique(user_id, fingerprint_hash)
);
create index if not exists idx_kit2_devices_user on public.koja_identity_v2_devices(user_id, last_seen_at desc);

create table if not exists public.koja_identity_v2_audit_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  organization_id uuid null,
  event_type text not null,
  severity text not null default 'info',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_kit2_audit_user on public.koja_identity_v2_audit_events(user_id, created_at desc);
create index if not exists idx_kit2_audit_severity on public.koja_identity_v2_audit_events(severity, created_at desc);

alter table public.koja_identity_v2_verifications enable row level security;
alter table public.koja_identity_v2_devices enable row level security;
alter table public.koja_identity_v2_audit_events enable row level security;

drop policy if exists kit2_verification_owner on public.koja_identity_v2_verifications;
create policy kit2_verification_owner on public.koja_identity_v2_verifications for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists kit2_devices_owner on public.koja_identity_v2_devices;
create policy kit2_devices_owner on public.koja_identity_v2_devices for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists kit2_audit_owner on public.koja_identity_v2_audit_events;
create policy kit2_audit_owner on public.koja_identity_v2_audit_events for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
