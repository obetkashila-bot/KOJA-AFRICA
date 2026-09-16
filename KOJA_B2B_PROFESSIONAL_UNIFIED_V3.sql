-- KOJA B2B + PROFESSIONAL SERVICES UNIFIED V3
-- Additive/idempotent. Does not drop, recreate, or replace existing KOJA tables.
create extension if not exists pgcrypto;

create table if not exists public.koja_b2b_unified_listings (
  id uuid primary key default gen_random_uuid(),
  business_id uuid,
  owner_user_id uuid references auth.users(id) on delete set null,
  listing_type text not null default 'product',
  title text not null,
  description text default '',
  category text default '',
  profession text default '',
  service_mode text default 'project',
  location text default '',
  online_available boolean not null default true,
  price numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  unit text default 'service',
  active boolean not null default true,
  professional_provider_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_b2b_unified_listings_business_idx on public.koja_b2b_unified_listings(business_id,active,created_at desc);
create index if not exists koja_b2b_unified_listings_type_idx on public.koja_b2b_unified_listings(listing_type,category,active);

create table if not exists public.koja_b2b_unified_requests (
  id uuid primary key default gen_random_uuid(),
  buyer_business_id uuid,
  requester_user_id uuid references auth.users(id) on delete set null,
  request_type text not null default 'procurement',
  title text not null,
  description text default '',
  category text default '',
  profession text default '',
  location text default '',
  online_allowed boolean not null default true,
  budget numeric(18,2),
  currency text not null default 'ZMW',
  deadline timestamptz,
  status text not null default 'open',
  selected_quote_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_b2b_unified_requests_buyer_idx on public.koja_b2b_unified_requests(buyer_business_id,status,created_at desc);
create index if not exists koja_b2b_unified_requests_match_idx on public.koja_b2b_unified_requests(category,profession,status);

create table if not exists public.koja_b2b_unified_quotes (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.koja_b2b_unified_requests(id) on delete cascade,
  seller_business_id uuid,
  seller_user_id uuid references auth.users(id) on delete set null,
  professional_provider_id uuid,
  amount numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  delivery_days integer,
  proposal text default '',
  status text not null default 'submitted',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_b2b_unified_quotes_request_idx on public.koja_b2b_unified_quotes(request_id,status,created_at desc);

create table if not exists public.koja_b2b_unified_orders (
  id uuid primary key default gen_random_uuid(),
  request_id uuid references public.koja_b2b_unified_requests(id) on delete set null,
  quote_id uuid references public.koja_b2b_unified_quotes(id) on delete set null,
  buyer_business_id uuid,
  seller_business_id uuid,
  buyer_user_id uuid references auth.users(id) on delete set null,
  seller_user_id uuid references auth.users(id) on delete set null,
  professional_provider_id uuid,
  order_type text not null default 'b2b_service',
  amount numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  payment_status text not null default 'pending',
  fulfillment_status text not null default 'pending',
  delivery_status text not null default 'not_required',
  job_status text not null default 'not_started',
  external_reference text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_b2b_unified_orders_buyer_idx on public.koja_b2b_unified_orders(buyer_business_id,created_at desc);
create index if not exists koja_b2b_unified_orders_seller_idx on public.koja_b2b_unified_orders(seller_business_id,created_at desc);

create table if not exists public.koja_b2b_professional_links (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.koja_b2b_unified_listings(id) on delete cascade,
  professional_provider_id uuid,
  service_id uuid,
  service_model text not null default 'project',
  created_at timestamptz not null default now(),
  unique(listing_id)
);

create table if not exists public.koja_b2b_unified_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  business_id uuid,
  event_type text not null,
  entity_type text not null,
  entity_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists koja_b2b_unified_events_entity_idx on public.koja_b2b_unified_events(entity_type,entity_id,created_at desc);

alter table public.koja_b2b_unified_listings enable row level security;
alter table public.koja_b2b_unified_requests enable row level security;
alter table public.koja_b2b_unified_quotes enable row level security;
alter table public.koja_b2b_unified_orders enable row level security;
alter table public.koja_b2b_professional_links enable row level security;
alter table public.koja_b2b_unified_events enable row level security;

-- Server-side Flask uses the Supabase service key; these policies protect direct client access.
drop policy if exists "b2b listings public read active" on public.koja_b2b_unified_listings;
create policy "b2b listings public read active" on public.koja_b2b_unified_listings for select using (active = true or auth.uid() = owner_user_id);
drop policy if exists "b2b requests owner read" on public.koja_b2b_unified_requests;
create policy "b2b requests owner read" on public.koja_b2b_unified_requests for select using (auth.uid() = requester_user_id);
drop policy if exists "b2b quotes seller buyer read" on public.koja_b2b_unified_quotes;
create policy "b2b quotes seller buyer read" on public.koja_b2b_unified_quotes for select using (auth.uid() = seller_user_id or auth.uid() in (select requester_user_id from public.koja_b2b_unified_requests r where r.id=request_id));
drop policy if exists "b2b orders participants read" on public.koja_b2b_unified_orders;
create policy "b2b orders participants read" on public.koja_b2b_unified_orders for select using (auth.uid() = buyer_user_id or auth.uid() = seller_user_id);

-- Helpful status fields for existing B2B/professional systems where present.
alter table if exists public.koja_b2b_requests add column if not exists unified_request_id uuid;
alter table if exists public.koja_b2b_quotations add column if not exists unified_request_id uuid;
alter table if exists public.koja_b2b_purchase_orders add column if not exists unified_order_id uuid;
