-- KOJA AFRICA — ADDITIVE B2B + PROCUREMENT V1
-- Safe migration: CREATE TABLE IF NOT EXISTS only. No existing KOJA tables are dropped/recreated.

create extension if not exists pgcrypto;

create table if not exists public.koja_b2b_organizations (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid,
  name text not null,
  legal_name text,
  registration_number text,
  tax_number text,
  country text default 'ZM',
  currency text default 'ZMW',
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_b2b_members (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
  user_id uuid,
  role text default 'member',
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (organization_id, user_id)
);

create table if not exists public.koja_b2b_suppliers (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.koja_b2b_organizations(id) on delete set null,
  owner_id uuid,
  name text not null,
  category text,
  phone text,
  email text,
  address text,
  country text,
  verification_status text default 'pending',
  status text default 'pending',
  rating numeric(4,2) default 0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_b2b_rfqs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.koja_b2b_organizations(id) on delete set null,
  buyer_id uuid,
  title text not null,
  description text,
  due_date date,
  status text default 'open',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_b2b_rfq_items (
  id uuid primary key default gen_random_uuid(),
  rfq_id uuid references public.koja_b2b_rfqs(id) on delete cascade,
  description text not null,
  quantity numeric(18,4) default 1,
  unit text,
  target_price numeric(18,2),
  currency text default 'ZMW',
  created_at timestamptz default now()
);

create table if not exists public.koja_b2b_quotations (
  id uuid primary key default gen_random_uuid(),
  rfq_id uuid references public.koja_b2b_rfqs(id) on delete cascade,
  supplier_id uuid references public.koja_b2b_suppliers(id) on delete set null,
  quotation_number text,
  total_amount numeric(18,2) default 0,
  currency text default 'ZMW',
  valid_until date,
  terms text,
  status text default 'submitted',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_b2b_quotation_items (
  id uuid primary key default gen_random_uuid(),
  quotation_id uuid references public.koja_b2b_quotations(id) on delete cascade,
  description text not null,
  quantity numeric(18,4) default 1,
  unit_price numeric(18,2) default 0,
  total_price numeric(18,2) default 0,
  currency text default 'ZMW',
  created_at timestamptz default now()
);

create table if not exists public.koja_b2b_purchase_orders (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.koja_b2b_organizations(id) on delete set null,
  buyer_id uuid,
  supplier_id uuid references public.koja_b2b_suppliers(id) on delete set null,
  rfq_id uuid references public.koja_b2b_rfqs(id) on delete set null,
  quotation_id uuid references public.koja_b2b_quotations(id) on delete set null,
  po_number text unique,
  description text,
  total_amount numeric(18,2) default 0,
  currency text default 'ZMW',
  status text default 'draft',
  approval_status text default 'pending',
  expected_delivery_date date,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_b2b_purchase_order_items (
  id uuid primary key default gen_random_uuid(),
  purchase_order_id uuid references public.koja_b2b_purchase_orders(id) on delete cascade,
  description text not null,
  quantity numeric(18,4) default 1,
  unit_price numeric(18,2) default 0,
  total_price numeric(18,2) default 0,
  currency text default 'ZMW',
  created_at timestamptz default now()
);

create table if not exists public.koja_b2b_supplier_contracts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.koja_b2b_organizations(id) on delete set null,
  supplier_id uuid references public.koja_b2b_suppliers(id) on delete set null,
  contract_number text,
  title text,
  start_date date,
  end_date date,
  value numeric(18,2),
  currency text default 'ZMW',
  terms text,
  status text default 'draft',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_b2b_recurring_procurement (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.koja_b2b_organizations(id) on delete set null,
  buyer_id uuid,
  supplier_id uuid references public.koja_b2b_suppliers(id) on delete set null,
  title text not null,
  frequency text not null,
  next_run_at timestamptz,
  amount numeric(18,2) default 0,
  currency text default 'ZMW',
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.koja_b2b_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid,
  actor_id uuid,
  event_type text not null,
  entity_type text,
  entity_id uuid,
  payload jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create index if not exists idx_koja_b2b_members_user on public.koja_b2b_members(user_id);
create index if not exists idx_koja_b2b_members_org on public.koja_b2b_members(organization_id);
create index if not exists idx_koja_b2b_suppliers_org on public.koja_b2b_suppliers(organization_id);
create index if not exists idx_koja_b2b_rfqs_org on public.koja_b2b_rfqs(organization_id);
create index if not exists idx_koja_b2b_rfqs_buyer on public.koja_b2b_rfqs(buyer_id);
create index if not exists idx_koja_b2b_quotations_rfq on public.koja_b2b_quotations(rfq_id);
create index if not exists idx_koja_b2b_pos_org on public.koja_b2b_purchase_orders(organization_id);
create index if not exists idx_koja_b2b_pos_buyer on public.koja_b2b_purchase_orders(buyer_id);
create index if not exists idx_koja_b2b_pos_supplier on public.koja_b2b_purchase_orders(supplier_id);
create index if not exists idx_koja_b2b_contracts_supplier on public.koja_b2b_supplier_contracts(supplier_id);
create index if not exists idx_koja_b2b_recurring_org on public.koja_b2b_recurring_procurement(organization_id);
create index if not exists idx_koja_b2b_events_entity on public.koja_b2b_events(entity_type, entity_id);

-- RLS is intentionally enabled only on the new tables. Existing KOJA tables are untouched.
alter table public.koja_b2b_organizations enable row level security;
alter table public.koja_b2b_members enable row level security;
alter table public.koja_b2b_suppliers enable row level security;
alter table public.koja_b2b_rfqs enable row level security;
alter table public.koja_b2b_rfq_items enable row level security;
alter table public.koja_b2b_quotations enable row level security;
alter table public.koja_b2b_quotation_items enable row level security;
alter table public.koja_b2b_purchase_orders enable row level security;
alter table public.koja_b2b_purchase_order_items enable row level security;
alter table public.koja_b2b_supplier_contracts enable row level security;
alter table public.koja_b2b_recurring_procurement enable row level security;
alter table public.koja_b2b_events enable row level security;

-- Flask uses Supabase REST with the service role on the server, so no client policies
-- are required for this server-side V1. Add authenticated policies later if direct
-- browser access to these tables is introduced.
