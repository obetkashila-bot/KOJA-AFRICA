-- KOJA UNIFIED FULFILLMENT V3
-- Additive/idempotent migration. No DROP/TRUNCATE/DELETE.

alter table if exists public.koja_market_orders add column if not exists fulfillment_method text not null default 'delivery';
alter table if exists public.koja_market_orders add column if not exists self_pickup_location text;
alter table if exists public.koja_market_orders add column if not exists self_pickup_contact text;

alter table if exists public.koja_market_delivery_jobs add column if not exists seller_id uuid;
alter table if exists public.koja_market_delivery_jobs add column if not exists source_type text not null default 'market';
alter table if exists public.koja_market_delivery_jobs add column if not exists source_order_id uuid;
alter table if exists public.koja_market_delivery_jobs add column if not exists fulfillment_method text not null default 'delivery';

alter table if exists public.deliveries add column if not exists pickup_code text;
alter table if exists public.deliveries add column if not exists pickup_verified boolean not null default false;
alter table if exists public.deliveries add column if not exists picked_up_at timestamptz;
alter table if exists public.deliveries add column if not exists delivery_completed_at timestamptz;
alter table if exists public.deliveries add column if not exists driver_payout_status text;
alter table if exists public.deliveries add column if not exists driver_payout_reference text;
alter table if exists public.deliveries add column if not exists driver_payout_transfer_id text;

alter table if exists public.koja_business_products add column if not exists product_type text not null default 'physical';
alter table if exists public.koja_business_products add column if not exists delivery_available boolean not null default true;
alter table if exists public.koja_business_products add column if not exists delivery_fee numeric(12,2) not null default 0;

create table if not exists public.koja_business_orders (
 id uuid primary key default gen_random_uuid(),
 business_id uuid not null,
 product_id uuid not null,
 buyer_id uuid not null,
 quantity integer not null default 1,
 item_amount numeric(12,2) not null default 0,
 delivery_fee numeric(12,2) not null default 0,
 total_amount numeric(12,2) not null default 0,
 fulfillment_method text not null default 'delivery',
 delivery_address text,
 recipient_phone text,
 payment_reference text,
 payment_transaction_id text,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);

create index if not exists idx_koja_business_orders_business on public.koja_business_orders(business_id,created_at desc);
create index if not exists idx_koja_business_orders_buyer on public.koja_business_orders(buyer_id,created_at desc);
create index if not exists idx_koja_business_orders_status on public.koja_business_orders(status,created_at desc);
create index if not exists idx_koja_deliveries_available on public.deliveries(status,driver_id,created_at desc);
