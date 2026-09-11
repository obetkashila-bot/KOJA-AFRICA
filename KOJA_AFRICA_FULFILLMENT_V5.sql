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

-- ============================================================
-- KOJA FULFILLMENT HARDENING NEXT V7
-- Additive/idempotent production hardening.
-- ============================================================
create extension if not exists pgcrypto;

-- Business Store order ledger used by the production checkout/callback.
create table if not exists public.koja_business_orders (
    id uuid primary key default gen_random_uuid(),
    order_number text unique not null,
    business_id uuid not null references public.koja_businesses(id) on delete cascade,
    buyer_id uuid not null,
    product_id uuid references public.koja_business_products(id) on delete set null,
    quantity integer not null default 1 check (quantity > 0),
    item_amount numeric(14,2) not null default 0,
    delivery_fee numeric(14,2) not null default 0,
    total_amount numeric(14,2) not null default 0,
    currency text not null default 'ZMW',
    product_type text not null default 'physical',
    fulfillment_method text not null default 'delivery',
    delivery_address text,
    pickup_address text,
    customer_name text,
    customer_phone text,
    recipient_name text,
    recipient_phone text,
    payment_method text,
    payment_reference text,
    payment_transaction_id text,
    payment_status text not null default 'pending',
    status text not null default 'pending',
    delivery_status text not null default 'not_requested',
    tracking_code text,
    pickup_code text,
    driver_id uuid,
    digital_file_url text,
    digital_file_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.koja_business_orders add column if not exists payment_transaction_id text;
alter table public.koja_business_orders add column if not exists recipient_name text;
alter table public.koja_business_orders add column if not exists recipient_phone text;
alter table public.koja_business_orders add column if not exists pickup_address text;
alter table public.koja_business_orders add column if not exists delivery_status text not null default 'not_requested';
alter table public.koja_business_orders add column if not exists tracking_code text;
alter table public.koja_business_orders add column if not exists pickup_code text;
alter table public.koja_business_orders add column if not exists driver_id uuid;
alter table public.koja_business_orders add column if not exists digital_file_url text;
alter table public.koja_business_orders add column if not exists digital_file_name text;

create index if not exists koja_business_orders_business_idx on public.koja_business_orders(business_id, created_at desc);
create index if not exists koja_business_orders_buyer_idx on public.koja_business_orders(buyer_id, created_at desc);
create index if not exists koja_business_orders_status_idx on public.koja_business_orders(status, created_at desc);
create index if not exists koja_business_orders_payment_idx on public.koja_business_orders(payment_status, created_at desc);
create index if not exists koja_business_orders_tracking_idx on public.koja_business_orders(tracking_code) where tracking_code is not null;
create index if not exists koja_business_orders_driver_idx on public.koja_business_orders(driver_id) where driver_id is not null;

-- Compatibility columns used by Business Store and Market/Delivery integration.
alter table public.koja_business_products add column if not exists product_type text not null default 'physical';
alter table public.koja_business_products add column if not exists delivery_available boolean not null default true;
alter table public.koja_business_products add column if not exists delivery_fee numeric(14,2) not null default 0;
alter table public.koja_business_products add column if not exists digital_file_url text;
alter table public.koja_business_products add column if not exists digital_file_name text;

-- Atomic Market payment + inventory finalization.
create or replace function public.koja_finalize_market_order_atomic(
    p_order_id uuid,
    p_product_id uuid,
    p_quantity integer,
    p_payment_transaction_id text,
    p_payment_method text default 'flutterwave'
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    o public.koja_market_orders%rowtype;
    p public.koja_market_products%rowtype;
    new_stock integer;
begin
    if p_quantity is null or p_quantity <= 0 then
        return jsonb_build_object('ok', false, 'reason', 'invalid_quantity');
    end if;

    select * into o
    from public.koja_market_orders
    where id = p_order_id
    for update;

    if not found then
        return jsonb_build_object('ok', false, 'reason', 'order_not_found');
    end if;

    if lower(coalesce(o.status,'')) in ('paid','completed') then
        return jsonb_build_object('ok', true, 'already_paid', true, 'stock_remaining', null);
    end if;

    select * into p
    from public.koja_market_products
    where id = p_product_id
    for update;

    if not found then
        return jsonb_build_object('ok', false, 'reason', 'product_not_found');
    end if;

    if lower(coalesce(p.product_type,'physical')) = 'physical' then
        if coalesce(p.stock,0) < p_quantity then
            return jsonb_build_object('ok', false, 'reason', 'insufficient_stock', 'stock_available', coalesce(p.stock,0));
        end if;
        new_stock := greatest(0, coalesce(p.stock,0) - p_quantity);
        update public.koja_market_products
        set stock = new_stock,
            is_published = (new_stock > 0),
            updated_at = now()
        where id = p.id;
    else
        new_stock := p.stock;
    end if;

    update public.koja_market_orders
    set status = 'paid',
        payment_method = coalesce(p_payment_method, payment_method),
        payment_transaction_id = coalesce(p_payment_transaction_id, payment_transaction_id),
        payout_status = coalesce(payout_status, 'pending'),
        updated_at = now()
    where id = o.id;

    return jsonb_build_object('ok', true, 'already_paid', false, 'stock_remaining', new_stock);
exception when others then
    raise;
end;
$$;

revoke all on function public.koja_finalize_market_order_atomic(uuid,uuid,integer,text,text) from public;
grant execute on function public.koja_finalize_market_order_atomic(uuid,uuid,integer,text,text) to service_role;

-- Useful indexes for delivery discovery/claiming and pickup verification.
create index if not exists deliveries_available_driver_idx
on public.deliveries(status, driver_id, created_at desc)
where status = 'requested' and driver_id is null;
create index if not exists deliveries_tracking_code_idx
on public.deliveries(tracking_code)
where tracking_code is not null;
create index if not exists deliveries_pickup_code_idx
on public.deliveries(pickup_code)
where pickup_code is not null;

-- Never expose the pickup number through broad public delivery listings.
-- Application routes continue to enforce driver ownership before verification.
