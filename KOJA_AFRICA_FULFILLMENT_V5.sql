-- KOJA AFRICA UNIFIED FULFILLMENT V5 — additive production hardening
-- Safe: CREATE/ALTER/INDEX only. No DROP/TRUNCATE/DELETE.

create table if not exists public.koja_ai_approval_events (
 id uuid primary key default gen_random_uuid(),
 table_name text not null, item_id text not null, kind text not null,
 decision text not null, confidence numeric(6,5) not null default 0,
 reason text default '', source text not null default 'ai_auto', created_at timestamptz not null default now()
);
create index if not exists koja_ai_approval_events_item_idx on public.koja_ai_approval_events(table_name,item_id,created_at desc);
create index if not exists koja_ai_approval_events_decision_idx on public.koja_ai_approval_events(decision,created_at desc);
alter table if exists public.koja_ai_approval_events enable row level security;

-- Business digital products
alter table if exists public.koja_business_products add column if not exists digital_file_url text;
alter table if exists public.koja_business_products add column if not exists digital_file_name text;
alter table if exists public.koja_business_products add column if not exists market_product_id uuid;
create index if not exists koja_business_products_type_idx on public.koja_business_products(product_type,active);

-- Delivery state, security, payout and address compatibility
alter table if exists public.deliveries add column if not exists pickup_address text;
alter table if exists public.deliveries add column if not exists delivery_address text;
alter table if exists public.deliveries add column if not exists pickup_code text;
alter table if exists public.deliveries add column if not exists pickup_verified boolean default false;
alter table if exists public.deliveries add column if not exists picked_up_at timestamptz;
alter table if exists public.deliveries add column if not exists delivery_completed_at timestamptz;
alter table if exists public.deliveries add column if not exists driver_payout_status text default 'pending';
alter table if exists public.deliveries add column if not exists driver_payout_reference text;
alter table if exists public.deliveries add column if not exists driver_payout_transfer_id text;
create index if not exists koja_deliveries_available_idx on public.deliveries(status,driver_id,created_at desc);
create index if not exists koja_deliveries_tracking_idx on public.deliveries(tracking_code);

-- Market delivery job lifecycle
alter table if exists public.koja_market_delivery_jobs add column if not exists completed_at timestamptz;
alter table if exists public.koja_market_delivery_jobs add column if not exists source_type text;
alter table if exists public.koja_market_delivery_jobs add column if not exists source_order_id uuid;
create index if not exists koja_market_delivery_jobs_status_idx on public.koja_market_delivery_jobs(status,created_at desc);

-- Fulfillment AI audit
create table if not exists public.koja_fulfillment_ai_events (
 id uuid primary key default gen_random_uuid(), user_id uuid, kind text not null,
 request_data jsonb default '{}'::jsonb, response_text text default '',
 created_at timestamptz not null default now()
);
create index if not exists koja_fulfillment_ai_events_date_idx on public.koja_fulfillment_ai_events(created_at desc);
alter table if exists public.koja_fulfillment_ai_events enable row level security;

-- Notification foundation compatibility
create table if not exists public.koja_notifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 notification_type text, title text, body text, related_id uuid,
 is_read boolean default false, created_at timestamptz default now()
);
create index if not exists koja_notifications_user_idx on public.koja_notifications(user_id,is_read,created_at desc);
create table if not exists public.koja_notification_preferences (
 user_id uuid primary key, push_enabled boolean default true, sound_enabled boolean default true,
 market_enabled boolean default true, delivery_enabled boolean default true, ai_enabled boolean default true,
 messages_enabled boolean default true, system_enabled boolean default true, updated_at timestamptz default now()
);

-- Live Shopping
create table if not exists public.koja_market_live_rooms (
 id uuid primary key default gen_random_uuid(), seller_id uuid, room_id text unique not null,
 title text default '', status text default 'live', product_id uuid, created_at timestamptz default now(), ended_at timestamptz
);
create index if not exists koja_market_live_rooms_status_idx on public.koja_market_live_rooms(status,created_at desc);

-- Business orders / secure digital delivery compatibility
alter table if exists public.koja_business_orders add column if not exists fulfillment_method text default 'delivery';
alter table if exists public.koja_business_orders add column if not exists delivery_address text;
alter table if exists public.koja_business_orders add column if not exists recipient_phone text;
alter table if exists public.koja_business_orders add column if not exists payment_transaction_id text;
create index if not exists koja_business_orders_buyer_idx on public.koja_business_orders(buyer_id,created_at desc);

-- Revenue/profit compatibility is preserved by the existing Profit Engine migration.

-- Keep auto approval conservative by default.
-- Runtime values are controlled by Render environment variables:
-- KOJA_AI_AUTO_APPROVAL=true
-- KOJA_AI_AUTO_APPROVAL_THRESHOLD=0.90
