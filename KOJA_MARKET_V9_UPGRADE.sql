-- KOJA MARKET V9 — additive production migration
-- Safe: CREATE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS only.

create extension if not exists pgcrypto;

-- Seller wallet / payouts compatibility
create table if not exists public.koja_market_payouts (
  id uuid primary key default gen_random_uuid(),
  seller_id uuid not null,
  user_id uuid,
  amount numeric(14,2) not null default 0,
  currency text not null default 'ZMW',
  method text not null default 'mobile_money',
  destination text not null default '',
  status text not null default 'requested',
  admin_note text default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_market_payouts_seller_idx on public.koja_market_payouts(seller_id,status,created_at desc);

-- Buyer protection / dispute workflow
create table if not exists public.koja_market_protection_claims (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null,
  buyer_id uuid not null,
  seller_id uuid,
  reason text not null,
  description text default '',
  requested_amount numeric(14,2) not null default 0,
  status text not null default 'submitted',
  admin_note text default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists koja_market_protection_claim_order_buyer_idx on public.koja_market_protection_claims(order_id,buyer_id);
create index if not exists koja_market_protection_claim_status_idx on public.koja_market_protection_claims(status,created_at desc);

-- Escrow / settlement metadata. Existing order data is preserved.
alter table if exists public.koja_market_orders add column if not exists escrow_status text default 'not_applicable';
alter table if exists public.koja_market_orders add column if not exists escrow_amount numeric(14,2) default 0;
alter table if exists public.koja_market_orders add column if not exists escrow_released_at timestamptz;
alter table if exists public.koja_market_orders add column if not exists protection_until timestamptz;
alter table if exists public.koja_market_orders add column if not exists refund_status text default 'none';
alter table if exists public.koja_market_orders add column if not exists country_code text default 'ZM';
alter table if exists public.koja_market_orders add column if not exists customer_currency text default 'ZMW';
alter table if exists public.koja_market_orders add column if not exists exchange_rate numeric(18,8) default 1;
alter table if exists public.koja_market_orders add column if not exists notes text default '';
create index if not exists koja_market_orders_escrow_idx on public.koja_market_orders(escrow_status,created_at desc);

-- Product discovery / seller quality metadata, computed by the app but persisted when available.
alter table if exists public.koja_market_products add column if not exists country_code text default 'ZM';
alter table if exists public.koja_market_products add column if not exists latitude numeric(10,7);
alter table if exists public.koja_market_products add column if not exists longitude numeric(10,7);
alter table if exists public.koja_market_products add column if not exists view_count bigint not null default 0;
alter table if exists public.koja_market_products add column if not exists sold_count bigint not null default 0;
alter table if exists public.koja_market_products add column if not exists average_rating numeric(4,2) not null default 0;
create index if not exists koja_market_products_discovery_idx on public.koja_market_products(is_published,approval_status,category,created_at desc);
create index if not exists koja_market_products_country_idx on public.koja_market_products(country_code,category);

-- Seller country / payout preferences
alter table if exists public.koja_market_sellers add column if not exists country_code text default 'ZM';
alter table if exists public.koja_market_sellers add column if not exists currency text default 'ZMW';
alter table if exists public.koja_market_sellers add column if not exists latitude numeric(10,7);
alter table if exists public.koja_market_sellers add column if not exists longitude numeric(10,7);
alter table if exists public.koja_market_sellers add column if not exists payout_method text default 'mobile_money';
alter table if exists public.koja_market_sellers add column if not exists payout_destination text default '';

-- Delivery tracking metadata; compatible with existing driver integration.
alter table if exists public.koja_market_delivery_jobs add column if not exists country_code text default 'ZM';
alter table if exists public.koja_market_delivery_jobs add column if not exists eta_minutes numeric(10,2);
alter table if exists public.koja_market_delivery_jobs add column if not exists last_driver_update_at timestamptz;
create index if not exists koja_market_delivery_jobs_driver_status_idx on public.koja_market_delivery_jobs(driver_id,status,updated_at desc);

-- Lightweight analytics events for marketplace discovery, ads and conversion.
create table if not exists public.koja_market_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  product_id uuid,
  seller_id uuid,
  event_type text not null,
  session_key text default '',
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists koja_market_events_product_idx on public.koja_market_events(product_id,event_type,created_at desc);
create index if not exists koja_market_events_seller_idx on public.koja_market_events(seller_id,event_type,created_at desc);
create index if not exists koja_market_events_date_idx on public.koja_market_events(created_at desc);

-- Country/currency reference table for Africa expansion.
create table if not exists public.koja_market_countries (
  code text primary key,
  name text not null,
  currency text not null,
  currency_symbol text default '',
  is_active boolean not null default true
);
insert into public.koja_market_countries(code,name,currency,currency_symbol) values
('ZM','Zambia','ZMW','K'),('ZW','Zimbabwe','ZWG','$'),('MW','Malawi','MWK','MK'),
('TZ','Tanzania','TZS','TSh'),('KE','Kenya','KES','KSh'),('UG','Uganda','UGX','USh'),
('RW','Rwanda','RWF','FRw'),('GH','Ghana','GHS','GH₵'),('NG','Nigeria','NGN','₦'),
('ZA','South Africa','ZAR','R'),('BW','Botswana','BWP','P'),('MZ','Mozambique','MZN','MT'),
('NA','Namibia','NAD','N$'),('ZM','Zambia','ZMW','K')
on conflict (code) do update set name=excluded.name,currency=excluded.currency,currency_symbol=excluded.currency_symbol;

-- Useful status indexes for operational dashboards.
create index if not exists koja_market_orders_buyer_status_idx on public.koja_market_orders(buyer_id,status,created_at desc);
create index if not exists koja_market_orders_seller_status_idx on public.koja_market_orders(seller_id,status,created_at desc);
create index if not exists koja_market_reviews_product_idx on public.koja_market_reviews(product_id,created_at desc);

-- Existing notifications table is reused by Market; do not replace it.
