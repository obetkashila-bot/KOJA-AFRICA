-- KOJA AFRICA production-safe additive migration 2026-09-12
-- Run in Supabase SQL Editor. Does not drop/recreate existing tables.

create table if not exists public.koja_business_orders (
  id uuid primary key default gen_random_uuid(),
  business_id uuid,
  product_id uuid,
  buyer_id uuid,
  quantity integer not null default 1,
  item_amount numeric(14,2) not null default 0,
  delivery_fee numeric(14,2) not null default 0,
  total_amount numeric(14,2) not null default 0,
  fulfillment_method text not null default 'self_pickup',
  delivery_address text,
  recipient_phone text,
  payment_reference text,
  payment_transaction_id text,
  currency text not null default 'ZMW',
  status text not null default 'pending',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table if exists public.koja_business_orders add column if not exists business_id uuid;
alter table if exists public.koja_business_orders add column if not exists product_id uuid;
alter table if exists public.koja_business_orders add column if not exists buyer_id uuid;
alter table if exists public.koja_business_orders add column if not exists quantity integer default 1;
alter table if exists public.koja_business_orders add column if not exists item_amount numeric(14,2) default 0;
alter table if exists public.koja_business_orders add column if not exists delivery_fee numeric(14,2) default 0;
alter table if exists public.koja_business_orders add column if not exists total_amount numeric(14,2) default 0;
alter table if exists public.koja_business_orders add column if not exists fulfillment_method text default 'self_pickup';
alter table if exists public.koja_business_orders add column if not exists delivery_address text;
alter table if exists public.koja_business_orders add column if not exists recipient_phone text;
alter table if exists public.koja_business_orders add column if not exists payment_reference text;
alter table if exists public.koja_business_orders add column if not exists payment_transaction_id text;
alter table if exists public.koja_business_orders add column if not exists currency text default 'ZMW';
alter table if exists public.koja_business_orders add column if not exists status text default 'pending';
alter table if exists public.koja_business_orders add column if not exists created_at timestamptz default now();
alter table if exists public.koja_business_orders add column if not exists updated_at timestamptz default now();
create index if not exists koja_business_orders_buyer_idx on public.koja_business_orders(buyer_id,created_at desc);
create index if not exists koja_business_orders_business_idx on public.koja_business_orders(business_id,created_at desc);
create index if not exists koja_business_orders_status_idx on public.koja_business_orders(status,created_at desc);
create unique index if not exists koja_business_orders_payment_ref_uidx on public.koja_business_orders(payment_reference) where payment_reference is not null;

create table if not exists public.koja_push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  endpoint text not null,
  subscription jsonb not null default '{}'::jsonb,
  user_agent text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique(user_id,endpoint)
);
create index if not exists koja_push_subscriptions_user_idx on public.koja_push_subscriptions(user_id,created_at desc);

create table if not exists public.koja_media_events (
  id uuid primary key default gen_random_uuid(),
  post_id uuid,
  user_id uuid,
  session_id text not null default '',
  event_type text not null default 'impression',
  watch_seconds numeric default 0,
  completion_percent numeric default 0,
  created_at timestamptz default now()
);
alter table if exists public.koja_media_events add column if not exists event_type text default 'impression';
alter table if exists public.koja_media_events add column if not exists session_id text default '';
alter table if exists public.koja_media_events add column if not exists watch_seconds numeric default 0;
alter table if exists public.koja_media_events add column if not exists completion_percent numeric default 0;
create index if not exists koja_media_events_post_event_idx on public.koja_media_events(post_id,event_type,created_at desc);

create table if not exists public.koja_user_service_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  service_key text,
  event_type text,
  object_id text,
  country_code text default 'ZM',
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
alter table if exists public.koja_user_service_events add column if not exists service_key text;
alter table if exists public.koja_user_service_events add column if not exists event_type text;
alter table if exists public.koja_user_service_events add column if not exists object_id text;
alter table if exists public.koja_user_service_events add column if not exists country_code text default 'ZM';
alter table if exists public.koja_user_service_events add column if not exists metadata jsonb default '{}'::jsonb;
alter table if exists public.koja_user_service_events add column if not exists created_at timestamptz default now();
create index if not exists koja_user_service_events_user_idx on public.koja_user_service_events(user_id,created_at desc);
create index if not exists koja_user_service_events_service_idx on public.koja_user_service_events(service_key,event_type,created_at desc);
