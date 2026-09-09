-- KOJA V8 Market Delivery V2 -- production hardening
-- Safe/idempotent. Does not modify Communications/WebRTC/FCM/LiveKit.

alter table public.koja_market_delivery_jobs add column if not exists route_distance_km numeric(12,3);
alter table public.koja_market_delivery_jobs add column if not exists route_duration_minutes integer;
alter table public.koja_market_delivery_jobs add column if not exists route_geometry jsonb;
alter table public.koja_market_delivery_jobs add column if not exists rejected_driver_id uuid;
alter table public.koja_market_delivery_jobs add column if not exists rejection_count integer not null default 0;
alter table public.koja_market_delivery_jobs add column if not exists last_status_at timestamptz default now();

create table if not exists public.koja_market_delivery_earnings (
 id uuid primary key default gen_random_uuid(),
 delivery_job_id uuid not null unique references public.koja_market_delivery_jobs(id) on delete cascade,
 order_id uuid,
 driver_id uuid not null,
 gross_fee numeric(14,2) not null default 0,
 driver_amount numeric(14,2) not null default 0,
 koja_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'earned',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_delivery_earnings_driver_idx on public.koja_market_delivery_earnings(driver_id,status,created_at desc);

create index if not exists koja_market_delivery_jobs_status_idx on public.koja_market_delivery_jobs(status,created_at desc);
create index if not exists koja_market_delivery_jobs_coords_idx on public.koja_market_delivery_jobs(pickup_latitude,pickup_longitude,status);

-- Prevent duplicate earnings for the same completed delivery.
create unique index if not exists koja_market_delivery_earnings_job_uidx on public.koja_market_delivery_earnings(delivery_job_id);

-- ============================================================
-- KOJA AFRICA SCALE REVENUE ENGINE V1
-- Safe/idempotent; does not modify Communications.
-- ============================================================
create table if not exists public.koja_revenue_payments (
  id uuid primary key default gen_random_uuid(), user_id uuid, kind text not null,
  item_key text not null, amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
  tx_ref text unique, transaction_id text, status text not null default 'pending',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_revenue_payments_user_idx on public.koja_revenue_payments(user_id,created_at desc);
create index if not exists koja_revenue_payments_status_idx on public.koja_revenue_payments(status,created_at desc);

create table if not exists public.koja_revenue_subscriptions (
  id uuid primary key default gen_random_uuid(), user_id uuid not null unique,
  plan text not null, monthly_price numeric(14,2) not null default 0, status text not null default 'active',
  started_at timestamptz default now(), expires_at timestamptz, created_at timestamptz default now(), updated_at timestamptz default now()
);

create table if not exists public.koja_revenue_events (
  id uuid primary key default gen_random_uuid(), user_id uuid, stream text not null,
  amount numeric(14,2) not null default 0, currency text not null default 'ZMW', related_id uuid,
  metadata jsonb default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists koja_revenue_events_stream_idx on public.koja_revenue_events(stream,created_at desc);

create table if not exists public.koja_ad_campaigns (
  id uuid primary key default gen_random_uuid(), user_id uuid not null, title text not null,
  product_id uuid, budget numeric(14,2) not null default 0, spent numeric(14,2) not null default 0,
  paid_amount numeric(14,2) not null default 0, status text not null default 'pending_payment',
  created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_ad_campaigns_user_idx on public.koja_ad_campaigns(user_id,created_at desc);

create table if not exists public.koja_procurement_requests (
  id uuid primary key default gen_random_uuid(), buyer_id uuid not null, item text not null,
  quantity integer not null default 1, target_budget numeric(14,2) default 0, status text not null default 'open',
  supplier_id uuid, agreed_amount numeric(14,2) default 0, koja_fee numeric(14,2) default 0,
  created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_procurement_requests_status_idx on public.koja_procurement_requests(status,created_at desc);
create index if not exists koja_procurement_requests_buyer_idx on public.koja_procurement_requests(buyer_id,created_at desc);

create table if not exists public.koja_enterprise_accounts (
  id uuid primary key default gen_random_uuid(), user_id uuid not null, company_name text not null,
  use_case text not null, monthly_volume numeric(16,2) default 0, status text not null default 'lead',
  created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_enterprise_accounts_status_idx on public.koja_enterprise_accounts(status,created_at desc);

alter table if exists public.koja_market_orders add column if not exists platform_fee numeric(14,2) default 0;
alter table if exists public.koja_market_orders add column if not exists driver_fee numeric(14,2) default 0;
alter table if exists public.koja_market_orders add column if not exists country_code text default 'ZM';
create index if not exists koja_market_orders_country_idx on public.koja_market_orders(country_code,created_at desc);
