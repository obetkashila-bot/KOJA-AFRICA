-- KOJA GLOBAL IMPORT & EXPORT / CUSTOMS ENGINE V1
-- Additive/update-safe migration. No existing tables are dropped or recreated.

create extension if not exists pgcrypto;

create table if not exists public.koja_global_trade_orders (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  created_by uuid,
  trade_code text not null unique,
  direction text not null default 'import',
  title text not null,
  origin_country text,
  destination_country text,
  currency text not null default 'ZMW',
  hs_code text,
  goods_value numeric(18,2) not null default 0,
  freight_cost numeric(18,2) not null default 0,
  insurance_cost numeric(18,2) not null default 0,
  origin_charges numeric(18,2) not null default 0,
  customs_value numeric(18,2) not null default 0,
  duty_rate numeric(9,4) not null default 0,
  duty_amount numeric(18,2) not null default 0,
  tax_rate numeric(9,4) not null default 0,
  tax_amount numeric(18,2) not null default 0,
  customs_fee numeric(18,2) not null default 0,
  broker_fee numeric(18,2) not null default 0,
  port_fee numeric(18,2) not null default 0,
  local_delivery_cost numeric(18,2) not null default 0,
  other_destination_cost numeric(18,2) not null default 0,
  destination_fees numeric(18,2) not null default 0,
  landed_cost numeric(18,2) not null default 0,
  status text not null default 'draft',
  customs_status text not null default 'not_started',
  clearance_status text not null default 'not_started',
  tracking_number text,
  carrier text,
  broker_name text,
  entry_port text,
  customs_reference text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_koja_global_trade_orders_business on public.koja_global_trade_orders(business_id, created_at desc);
create index if not exists idx_koja_global_trade_orders_status on public.koja_global_trade_orders(status, customs_status, clearance_status);

create table if not exists public.koja_global_trade_documents (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  trade_id uuid not null,
  document_type text not null,
  reference text,
  file_url text,
  status text not null default 'required',
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_koja_global_trade_documents_trade on public.koja_global_trade_documents(trade_id, created_at desc);

create table if not exists public.koja_global_trade_brokers (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  trade_id uuid not null,
  name text not null,
  country text,
  contact text,
  license_number text,
  status text not null default 'assigned',
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_koja_global_trade_brokers_trade on public.koja_global_trade_brokers(trade_id, created_at desc);

create table if not exists public.koja_global_trade_events (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  trade_id uuid not null,
  event_type text not null,
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_by uuid,
  created_at timestamptz not null default now()
);
create index if not exists idx_koja_global_trade_events_trade on public.koja_global_trade_events(trade_id, created_at desc);

create table if not exists public.koja_global_trade_audit (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  user_id uuid,
  action text not null,
  object_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_koja_global_trade_audit_business on public.koja_global_trade_audit(business_id, created_at desc);

-- Future country-specific customs rules can be added here without hard-coding
-- universal duty/tax rates into the application.
create table if not exists public.koja_global_customs_rules (
  id uuid primary key default gen_random_uuid(),
  country_code text not null,
  hs_code text,
  rule_name text not null,
  duty_rate numeric(9,4),
  tax_rate numeric(9,4),
  permit_required boolean not null default false,
  document_requirements jsonb not null default '[]'::jsonb,
  effective_from date,
  effective_to date,
  source_authority text,
  source_reference text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_koja_global_customs_rules_country_hs on public.koja_global_customs_rules(country_code, hs_code, active);
