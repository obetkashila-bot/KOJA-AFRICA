-- KOJA V8 remaining modules: Business POS, Seller Center, Marketplace ledger, payouts, revenue, AI subscription sync.
-- SAFE / IDEMPOTENT. Does not delete or recreate existing business or marketplace data.

create extension if not exists pgcrypto;

-- Business/POS hardening
alter table if exists public.koja_business_products add column if not exists cost_price numeric(14,2) not null default 0;
alter table if exists public.koja_business_products add column if not exists is_active boolean not null default true;
alter table if exists public.koja_business_products add column if not exists updated_at timestamptz not null default now();

alter table if exists public.koja_business_sales add column if not exists sale_number text;
alter table if exists public.koja_business_sales add column if not exists payment_method text default 'cash';
alter table if exists public.koja_business_sales add column if not exists updated_at timestamptz not null default now();
create unique index if not exists koja_business_sales_sale_number_uidx on public.koja_business_sales(sale_number) where sale_number is not null;

alter table if exists public.koja_business_sale_items add column if not exists unit_price numeric(14,2) not null default 0;
alter table if exists public.koja_business_sale_items add column if not exists subtotal numeric(14,2) not null default 0;

alter table if exists public.koja_business_expenses add column if not exists category text default 'General';
alter table if exists public.koja_business_expenses add column if not exists expense_date date;
alter table if exists public.koja_business_expenses add column if not exists updated_at timestamptz not null default now();

-- AI subscription compatibility for Business billing.
alter table if exists public.koja_ai_subscriptions add column if not exists monthly_price numeric(14,2) default 0;
alter table if exists public.koja_ai_subscriptions add column if not exists updated_at timestamptz not null default now();

-- Marketplace financial ledger: every paid marketplace order gets one immutable accounting row.
create table if not exists public.koja_marketplace_ledger (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null unique references public.koja_marketplace_orders(id) on delete cascade,
  seller_id uuid not null,
  buyer_id uuid,
  gross_amount numeric(14,2) not null default 0,
  koja_commission numeric(14,2) not null default 0,
  seller_amount numeric(14,2) not null default 0,
  currency text not null default 'ZMW',
  transaction_id text,
  status text not null default 'posted',
  created_at timestamptz not null default now()
);
create index if not exists koja_marketplace_ledger_seller_idx on public.koja_marketplace_ledger(seller_id, created_at desc);
create index if not exists koja_marketplace_ledger_status_idx on public.koja_marketplace_ledger(status, created_at desc);
create index if not exists koja_marketplace_ledger_tx_idx on public.koja_marketplace_ledger(transaction_id);

-- Seller payout requests. Actual money movement remains an admin-controlled payout operation.
create table if not exists public.koja_seller_payouts (
  id uuid primary key default gen_random_uuid(),
  seller_id uuid not null,
  amount numeric(14,2) not null check (amount > 0),
  currency text not null default 'ZMW',
  method text not null default 'mobile_money',
  account_reference text not null,
  status text not null default 'requested',
  provider_reference text,
  admin_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_seller_payouts_seller_idx on public.koja_seller_payouts(seller_id, created_at desc);
create index if not exists koja_seller_payouts_status_idx on public.koja_seller_payouts(status, created_at desc);

-- Business payment audit indexes/compatibility.
alter table if exists public.koja_business_payments add column if not exists transaction_id text;
alter table if exists public.koja_business_payments add column if not exists plan text;
alter table if exists public.koja_business_payments add column if not exists verified_at timestamptz;
alter table if exists public.koja_business_payments add column if not exists updated_at timestamptz not null default now();
create unique index if not exists koja_business_payments_reference_uidx on public.koja_business_payments(reference) where reference is not null;

-- Helpful revenue indexes.
create index if not exists koja_marketplace_orders_status_created_idx on public.koja_marketplace_orders(status, created_at desc);
create index if not exists koja_business_payments_status_created_idx on public.koja_business_payments(status, created_at desc);

-- Do not alter Communications tables, WebRTC, FCM, LiveKit, or driver communication routes.
-- KOJA V8 MARKET COMPLETE
-- Safe/idempotent migration for the existing physical + digital Marketplace.
-- Does not delete/recreate existing Market data or touch Communications.

create extension if not exists pgcrypto;

-- Existing Market tables: compatibility columns.
alter table if exists public.koja_market_products add column if not exists product_type text default 'physical';
alter table if exists public.koja_market_products add column if not exists stock integer default 1;
alter table if exists public.koja_market_products add column if not exists sku text;
alter table if exists public.koja_market_products add column if not exists image_url text;
alter table if exists public.koja_market_products add column if not exists digital_file_url text;
alter table if exists public.koja_market_products add column if not exists digital_file_name text;
alter table if exists public.koja_market_products add column if not exists delivery_available boolean default true;
alter table if exists public.koja_market_products add column if not exists delivery_fee numeric(14,2) default 0;
alter table if exists public.koja_market_products add column if not exists location text;
alter table if exists public.koja_market_products add column if not exists approval_status text default 'pending';
alter table if exists public.koja_market_products add column if not exists is_published boolean default false;

alter table if exists public.koja_market_sellers add column if not exists verification_status text default 'pending';
alter table if exists public.koja_market_sellers add column if not exists verification_id_url text;
alter table if exists public.koja_market_sellers add column if not exists verification_business_url text;
alter table if exists public.koja_market_sellers add column if not exists updated_at timestamptz not null default now();

-- Seller subscriptions and advertising/featured listings.
create table if not exists public.koja_market_seller_subscriptions (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null references public.koja_market_sellers(id) on delete cascade,
 user_id uuid not null,
 plan text not null default 'free',
 monthly_price numeric(14,2) not null default 0,
 status text not null default 'pending',
 payment_reference text,
 provider text,
 started_at timestamptz,
 expires_at timestamptz,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(seller_id)
);
create index if not exists koja_market_seller_subs_user_idx on public.koja_market_seller_subscriptions(user_id,status);

create table if not exists public.koja_market_featured (
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references public.koja_market_products(id) on delete cascade,
 seller_id uuid not null,
 days integer not null default 7,
 price numeric(14,2) not null default 0,
 status text not null default 'pending',
 starts_at timestamptz,
 ends_at timestamptz,
 created_at timestamptz not null default now()
);
create index if not exists koja_market_featured_active_idx on public.koja_market_featured(status,ends_at);

create table if not exists public.koja_market_ads (
 id uuid primary key default gen_random_uuid(),
 advertiser_id uuid not null,
 title text not null,
 target_url text,
 placement text not null default 'market',
 budget numeric(14,2) not null default 0,
 spent numeric(14,2) not null default 0,
 status text not null default 'pending',
 billing_status text not null default 'unbilled',
 impressions bigint not null default 0,
 clicks bigint not null default 0,
 starts_at timestamptz,
 ends_at timestamptz,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_ads_status_idx on public.koja_market_ads(status,placement);

create table if not exists public.koja_market_reviews (
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references public.koja_market_products(id) on delete cascade,
 buyer_id uuid not null,
 rating integer not null check(rating between 1 and 5),
 review text default '',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(product_id,buyer_id)
);

-- Marketplace financial ledger: 10% KOJA / 90% seller.
create table if not exists public.koja_market_ledger (
 id uuid primary key default gen_random_uuid(),
 order_id uuid references public.koja_market_orders(id) on delete set null,
 seller_id uuid not null,
 buyer_id uuid,
 gross_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0,
 platform_fee numeric(14,2) not null default 0,
 net_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 created_at timestamptz not null default now()
);
create unique index if not exists koja_market_ledger_order_uidx on public.koja_market_ledger(order_id) where order_id is not null;
create index if not exists koja_market_ledger_seller_idx on public.koja_market_ledger(seller_id,created_at desc);

create table if not exists public.koja_market_payouts (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 user_id uuid not null,
 amount numeric(14,2) not null check(amount>0),
 currency text not null default 'ZMW',
 method text not null default 'mobile_money',
 destination text not null,
 status text not null default 'requested',
 provider_reference text,
 admin_note text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_payouts_seller_idx on public.koja_market_payouts(seller_id,status,created_at desc);

-- Referrals.
create table if not exists public.koja_referral_codes (
 id uuid primary key default gen_random_uuid(),
 user_id uuid unique not null,
 code text unique not null,
 active boolean not null default true,
 created_at timestamptz not null default now()
);
create table if not exists public.koja_referrals (
 id uuid primary key default gen_random_uuid(),
 referrer_id uuid not null,
 referred_user_id uuid not null,
 code text not null,
 status text not null default 'registered',
 reward_amount numeric(14,2) not null default 0,
 created_at timestamptz not null default now(),
 unique(referrer_id,referred_user_id)
);
create index if not exists koja_referrals_referrer_idx on public.koja_referrals(referrer_id,created_at desc);

-- Useful order/payment indexes.
create index if not exists koja_market_orders_payment_reference_idx on public.koja_market_orders(payment_reference);
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);

-- Keep the existing Business/POS and AI migrations compatible.
alter table if exists public.koja_ai_subscriptions add column if not exists monthly_price numeric(14,2) default 0;

-- Never modify Communications, WebRTC, FCM or LiveKit tables here.

-- ============================================================
-- KOJA V8 MARKET PHYSICAL DELIVERY GPS V1
-- SHOP -> ROAD -> HOME
-- Safe/idempotent migration. Does not modify Communications.
-- ============================================================

alter table public.koja_market_products add column if not exists pickup_latitude double precision;
alter table public.koja_market_products add column if not exists pickup_longitude double precision;

alter table public.koja_market_sellers add column if not exists address text;
alter table public.koja_market_sellers add column if not exists latitude double precision;
alter table public.koja_market_sellers add column if not exists longitude double precision;

alter table public.koja_market_orders add column if not exists delivery_latitude double precision;
alter table public.koja_market_orders add column if not exists delivery_longitude double precision;
alter table public.koja_market_orders add column if not exists notes text;
alter table public.koja_market_orders add column if not exists delivery_status text not null default 'not_requested';

alter table public.koja_market_delivery_jobs add column if not exists pickup_latitude double precision;
alter table public.koja_market_delivery_jobs add column if not exists pickup_longitude double precision;
alter table public.koja_market_delivery_jobs add column if not exists delivery_latitude double precision;
alter table public.koja_market_delivery_jobs add column if not exists delivery_longitude double precision;
alter table public.koja_market_delivery_jobs add column if not exists customer_phone text;
alter table public.koja_market_delivery_jobs add column if not exists seller_phone text;
alter table public.koja_market_delivery_jobs add column if not exists distance_km numeric(12,3);
alter table public.koja_market_delivery_jobs add column if not exists delivery_otp_hash text;
alter table public.koja_market_delivery_jobs add column if not exists delivery_otp text;
alter table public.koja_market_delivery_jobs add column if not exists last_known_driver_latitude double precision;
alter table public.koja_market_delivery_jobs add column if not exists last_known_driver_longitude double precision;
alter table public.koja_market_delivery_jobs add column if not exists last_known_driver_accuracy double precision;
create index if not exists koja_market_delivery_jobs_driver_status_idx on public.koja_market_delivery_jobs(driver_id,status,updated_at desc);
create index if not exists koja_market_delivery_jobs_customer_idx on public.koja_market_delivery_jobs(customer_id,created_at desc);
create index if not exists koja_market_delivery_jobs_tracking_idx on public.koja_market_delivery_jobs(tracking_code);
