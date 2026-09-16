-- KOJA B2B V4 COMPLETE TRANSACTION ENGINE
-- Additive / update-safe. Does not recreate or drop business data.

create table if not exists koja_b2b_v4_quotes (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null,
  seller_business_id uuid not null,
  seller_user_id uuid not null,
  professional_provider_id uuid null,
  amount numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  delivery_days integer not null default 1,
  proposal text,
  status text not null default 'submitted',
  accepted_at timestamptz,
  rejected_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists koja_b2b_v4_orders (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null,
  quote_id uuid not null,
  buyer_business_id uuid not null,
  buyer_user_id uuid not null,
  seller_business_id uuid not null,
  seller_user_id uuid not null,
  professional_provider_id uuid null,
  order_type text not null default 'b2b_service',
  amount numeric(18,2) not null default 0,
  platform_fee numeric(18,2) not null default 0,
  professional_fee numeric(18,2) not null default 0,
  seller_net numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  payment_status text not null default 'unpaid',
  payment_reference text unique,
  payment_transaction_id text,
  order_status text not null default 'awaiting_payment',
  fulfillment_status text not null default 'not_started',
  delivery_id uuid,
  delivery_address text,
  completion_note text,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists koja_b2b_v4_order_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null,
  listing_id uuid,
  description text not null,
  quantity numeric(18,3) not null default 1,
  unit_price numeric(18,2) not null default 0,
  total numeric(18,2) not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists koja_b2b_v4_events (
  id uuid primary key default gen_random_uuid(),
  order_id uuid,
  request_id uuid,
  actor_user_id uuid,
  actor_business_id uuid,
  event_type text not null,
  old_status text,
  new_status text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists koja_b2b_v4_ledger (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null,
  buyer_business_id uuid,
  seller_business_id uuid,
  professional_provider_id uuid,
  gross_amount numeric(18,2) not null default 0,
  platform_fee numeric(18,2) not null default 0,
  seller_amount numeric(18,2) not null default 0,
  professional_amount numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  status text not null default 'pending',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists koja_b2b_v4_reviews (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null,
  reviewer_user_id uuid not null,
  seller_business_id uuid,
  professional_provider_id uuid,
  rating integer not null check (rating between 1 and 5),
  review text,
  created_at timestamptz not null default now(),
  unique(order_id, reviewer_user_id)
);

create index if not exists idx_koja_b2b_v4_quotes_request on koja_b2b_v4_quotes(request_id);
create index if not exists idx_koja_b2b_v4_orders_buyer on koja_b2b_v4_orders(buyer_business_id);
create index if not exists idx_koja_b2b_v4_orders_seller on koja_b2b_v4_orders(seller_business_id);
create index if not exists idx_koja_b2b_v4_events_order on koja_b2b_v4_events(order_id, created_at desc);

-- RLS is additive. Policies are deliberately limited to participants.
alter table koja_b2b_v4_quotes enable row level security;
alter table koja_b2b_v4_orders enable row level security;
alter table koja_b2b_v4_order_items enable row level security;
alter table koja_b2b_v4_events enable row level security;
alter table koja_b2b_v4_ledger enable row level security;
alter table koja_b2b_v4_reviews enable row level security;


alter table koja_b2b_v4_orders add column if not exists delivery_address text;
