-- KOJA AFRICA End-to-End Service Engine V1
-- ADDITIVE ONLY: no existing tables are recreated or dropped.
create extension if not exists pgcrypto;

create table if not exists public.koja_e2e_services (
 id uuid primary key default gen_random_uuid(), provider_id uuid, business_id uuid,
 name text not null, description text, category text, price numeric(18,2) not null default 0,
 currency text not null default 'ZMW', fulfillment_mode text not null default 'digital',
 status text not null default 'published', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_koja_e2e_services_status on public.koja_e2e_services(status);
create index if not exists idx_koja_e2e_services_provider on public.koja_e2e_services(provider_id);

create table if not exists public.koja_e2e_orders (
 id uuid primary key default gen_random_uuid(), service_id uuid, customer_id uuid, provider_id uuid, business_id uuid,
 quantity integer not null default 1, unit_amount numeric(18,2) not null default 0, gross_amount numeric(18,2) not null default 0,
 currency text not null default 'ZMW', status text not null default 'requested', fulfillment_mode text,
 notes text, completed_at timestamptz, settled_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_koja_e2e_orders_customer on public.koja_e2e_orders(customer_id,created_at desc);
create index if not exists idx_koja_e2e_orders_provider on public.koja_e2e_orders(provider_id,created_at desc);
create index if not exists idx_koja_e2e_orders_status on public.koja_e2e_orders(status);

create table if not exists public.koja_e2e_order_events (
 id uuid primary key default gen_random_uuid(), order_id uuid not null, from_status text, to_status text not null,
 actor_id uuid, note text, created_at timestamptz not null default now()
);
create index if not exists idx_koja_e2e_order_events_order on public.koja_e2e_order_events(order_id,created_at);

create table if not exists public.koja_e2e_payments (
 id uuid primary key default gen_random_uuid(), order_id uuid not null, user_id uuid,
 provider text not null default 'flutterwave', payment_reference text not null unique,
 amount numeric(18,2) not null default 0, currency text not null default 'ZMW', status text not null default 'pending',
 transaction_id text, verified_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_koja_e2e_payments_order on public.koja_e2e_payments(order_id);

create table if not exists public.koja_e2e_fulfillments (
 id uuid primary key default gen_random_uuid(), order_id uuid not null, mode text not null, status text not null default 'requested',
 tracking_code text unique, driver_id uuid, address text, confirmation_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_koja_e2e_fulfillments_order on public.koja_e2e_fulfillments(order_id);

create table if not exists public.koja_e2e_earnings (
 id uuid primary key default gen_random_uuid(), order_id uuid not null, provider_id uuid, business_id uuid,
 gross_amount numeric(18,2) not null default 0, koja_fee numeric(18,2) not null default 0, net_amount numeric(18,2) not null default 0,
 currency text not null default 'ZMW', status text not null default 'pending', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_koja_e2e_earnings_provider on public.koja_e2e_earnings(provider_id,created_at desc);

create table if not exists public.koja_e2e_reviews (
 id uuid primary key default gen_random_uuid(), order_id uuid not null, reviewer_id uuid, provider_id uuid,
 rating integer not null check (rating between 1 and 5), review text, created_at timestamptz not null default now()
);
create unique index if not exists uq_koja_e2e_review_order_reviewer on public.koja_e2e_reviews(order_id,reviewer_id);

create table if not exists public.koja_e2e_disputes (
 id uuid primary key default gen_random_uuid(), order_id uuid not null, opened_by uuid, reason text, description text,
 status text not null default 'open', resolution text, resolved_by uuid, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_koja_e2e_disputes_order on public.koja_e2e_disputes(order_id);

create table if not exists public.koja_e2e_notifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, kind text not null default 'system',
 title text not null, body text, action_url text, entity_type text, entity_id uuid, is_read boolean not null default false,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_koja_e2e_notifications_user on public.koja_e2e_notifications(user_id,created_at desc);
create index if not exists idx_koja_e2e_notifications_unread on public.koja_e2e_notifications(user_id,is_read);

-- RLS is intentionally not enabled here because the application uses the existing Supabase REST service-key access pattern.
-- If client-side direct table access is later enabled, add explicit RLS policies before exposing these tables.
