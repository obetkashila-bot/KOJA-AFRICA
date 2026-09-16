-- KOJA GLOBAL BUSINESS V7
-- Complete Business Connect migration
-- Additive/update-safe: no table recreation and no data deletion.

create extension if not exists pgcrypto;

-- Existing KOJA business identity table receives the permanent public code.
alter table if exists public.koja_businesses
  add column if not exists business_code text;

alter table if exists public.koja_businesses
  add column if not exists verified boolean default false;

create unique index if not exists koja_businesses_business_code_uidx
  on public.koja_businesses (business_code)
  where business_code is not null;

-- Public business-code registry. Internal business UUIDs are never exposed to users.
create table if not exists public.koja_business_codes (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  public_code text not null unique,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists koja_business_codes_business_idx
  on public.koja_business_codes (business_id);

create index if not exists koja_business_codes_status_idx
  on public.koja_business_codes (status);

-- Business workforce membership for organisation-level access.
create table if not exists public.koja_business_members (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  user_id uuid not null,
  role text not null default 'member',
  permissions jsonb not null default '[]'::jsonb,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_id, user_id)
);

create index if not exists koja_business_members_user_idx
  on public.koja_business_members (user_id, status);

create index if not exists koja_business_members_business_idx
  on public.koja_business_members (business_id, status);

-- The relationship itself is separate from transactions.
-- business_a_id/business_b_id are stored in deterministic order.
create table if not exists public.koja_business_connections (
  id uuid primary key default gen_random_uuid(),
  business_a_id uuid not null,
  business_b_id uuid not null,
  requested_by_business_id uuid not null,
  status text not null default 'pending',
  relationship_type text not null default 'partner',
  created_at timestamptz not null default now(),
  accepted_at timestamptz,
  disconnected_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint koja_business_connections_no_self check (business_a_id <> business_b_id),
  constraint koja_business_connections_status_check check (status in ('pending','accepted','rejected','blocked','disconnected','revoked')),
  constraint koja_business_connections_unique_pair unique (business_a_id, business_b_id)
);

create index if not exists koja_business_connections_a_idx
  on public.koja_business_connections (business_a_id, status, updated_at desc);

create index if not exists koja_business_connections_b_idx
  on public.koja_business_connections (business_b_id, status, updated_at desc);

-- Per-business permissions on a connection.
create table if not exists public.koja_business_connection_permissions (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid not null,
  business_id uuid not null,
  permissions jsonb not null default '["profile","connect_plus","relationship_activity"]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (connection_id, business_id)
);

create index if not exists koja_business_connection_permissions_business_idx
  on public.koja_business_connection_permissions (business_id, connection_id);

-- Human-readable relationship contacts are distinct from KOJA user accounts.
create table if not exists public.koja_business_relationship_contacts (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid not null,
  business_id uuid not null,
  name text not null,
  role text,
  email text,
  phone text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists koja_business_relationship_contacts_idx
  on public.koja_business_relationship_contacts (connection_id, business_id);

create table if not exists public.koja_business_relationship_notes (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid not null,
  business_id uuid not null,
  author_user_id uuid,
  note text not null,
  created_at timestamptz not null default now()
);

create index if not exists koja_business_relationship_notes_idx
  on public.koja_business_relationship_notes (connection_id, business_id, created_at desc);

-- Complete relationship audit trail.
create table if not exists public.koja_business_relationship_activity (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid not null,
  actor_business_id uuid,
  event_type text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists koja_business_relationship_activity_idx
  on public.koja_business_relationship_activity (connection_id, created_at desc);

-- Shared document metadata. Actual bytes remain in KOJA/Supabase Storage.
create table if not exists public.koja_business_shared_documents (
  id uuid primary key default gen_random_uuid(),
  connection_id uuid not null,
  owner_business_id uuid not null,
  document_name text not null,
  storage_path text,
  mime_type text,
  visibility text not null default 'connection',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists koja_business_shared_documents_idx
  on public.koja_business_shared_documents (connection_id, created_at desc);

-- Optional relationship invites, useful for future QR/deep-link onboarding.
create table if not exists public.koja_business_connection_invites (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  invite_code text not null unique,
  expires_at timestamptz,
  max_uses integer not null default 1,
  used_count integer not null default 0,
  status text not null default 'active',
  created_at timestamptz not null default now()
);

create index if not exists koja_business_connection_invites_business_idx
  on public.koja_business_connection_invites (business_id, status);

-- Blocks prevent new relationship requests while preserving historical records.
create table if not exists public.koja_business_blocks (
  id uuid primary key default gen_random_uuid(),
  blocker_business_id uuid not null,
  blocked_business_id uuid not null,
  reason text,
  created_at timestamptz not null default now(),
  unique (blocker_business_id, blocked_business_id),
  constraint koja_business_blocks_no_self check (blocker_business_id <> blocked_business_id)
);

-- Generate codes for older businesses that do not have one yet.
-- The loop avoids collisions and does not overwrite an existing code.
do $$
declare
  b record;
  new_code text;
  alphabet text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  i integer;
  n integer;
begin
  if to_regclass('public.koja_businesses') is null then
    return;
  end if;

  for b in select id from public.koja_businesses where business_code is null loop
    loop
      new_code := 'KOJA-ZM-BUS-';
      for i in 1..6 loop
        n := 1 + floor(random() * length(alphabet))::integer;
        new_code := new_code || substr(alphabet, n, 1);
      end loop;
      exit when not exists (select 1 from public.koja_businesses x where x.business_code = new_code);
    end loop;

    update public.koja_businesses
       set business_code = new_code
     where id = b.id
       and business_code is null;

    insert into public.koja_business_codes (business_id, public_code)
    values (b.id, new_code)
    on conflict (public_code) do nothing;
  end loop;
end $$;

-- Backfill registry rows for businesses that already have a code.
insert into public.koja_business_codes (business_id, public_code)
select id, business_code
from public.koja_businesses
where business_code is not null
on conflict (public_code) do nothing;

-- Enable RLS on new relationship tables. The current Flask backend uses the
-- server-side Supabase key, so existing server routes continue to operate.
-- Direct browser access is therefore not required for these tables.
alter table public.koja_business_codes enable row level security;
alter table public.koja_business_members enable row level security;
alter table public.koja_business_connections enable row level security;
alter table public.koja_business_connection_permissions enable row level security;
alter table public.koja_business_relationship_contacts enable row level security;
alter table public.koja_business_relationship_notes enable row level security;
alter table public.koja_business_relationship_activity enable row level security;
alter table public.koja_business_shared_documents enable row level security;
alter table public.koja_business_connection_invites enable row level security;
alter table public.koja_business_blocks enable row level security;

-- No permissive anon policies are created. Flask server routes use the
-- SUPABASE_SERVICE_KEY and enforce business membership/ownership themselves.
