-- KOJA REGRESSION RESTORE / ADDITIVE MIGRATION 2026-09-20
-- Safe to run on the existing KOJA Supabase project. No DROP/RECREATE statements.

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

-- KOJA GLOBAL BUSINESS V5 additive operating layer
create table if not exists koja_global_business_disputes (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  opened_by uuid not null,
  order_id uuid null,
  reason text not null,
  description text,
  status text not null default 'open',
  resolution text,
  resolved_by uuid null,
  resolved_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_koja_global_business_disputes_business on koja_global_business_disputes(business_id,created_at desc);
create index if not exists idx_koja_global_business_disputes_order on koja_global_business_disputes(order_id);

create table if not exists koja_global_business_payouts (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  requested_by uuid not null,
  amount numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  method text not null default 'bank',
  provider_reference text,
  status text not null default 'requested',
  approved_by uuid null,
  approved_at timestamptz null,
  paid_at timestamptz null,
  failure_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists idx_koja_global_business_payouts_business on koja_global_business_payouts(business_id,created_at desc);
create index if not exists idx_koja_global_business_payouts_status on koja_global_business_payouts(status);

create table if not exists koja_global_business_events (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null,
  user_id uuid,
  event_type text not null,
  module text,
  entity_type text,
  entity_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_koja_global_business_events_business on koja_global_business_events(business_id,created_at desc);

alter table koja_global_business_disputes enable row level security;
alter table koja_global_business_payouts enable row level security;
alter table koja_global_business_events enable row level security;


-- KOJA GLOBAL BUSINESS V6
-- Additive, update-safe. No drops/recreates.

alter table koja_businesses add column if not exists country_code text;
alter table koja_businesses add column if not exists currency_code text default 'ZMW';
alter table koja_businesses add column if not exists timezone text default 'UTC';
alter table koja_businesses add column if not exists tax_id text;

create table if not exists koja_global_business_settings (
  id uuid primary key default gen_random_uuid(), business_id uuid not null, country_code text not null default 'ZM', currency_code text not null default 'ZMW', timezone text not null default 'UTC', tax_registration text, tax_rate numeric(8,4) not null default 0, language_code text not null default 'en', international_enabled boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists koja_global_business_roles (
  id uuid primary key default gen_random_uuid(), business_id uuid not null, user_id uuid not null, role_code text not null default 'staff', status text not null default 'active', permissions jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id,user_id)
);

create table if not exists koja_global_business_contracts (
  id uuid primary key default gen_random_uuid(), business_id uuid not null, counterparty_business_id uuid, title text not null, contract_type text not null default 'service', amount numeric(18,2), currency text not null default 'ZMW', start_date date, end_date date, status text not null default 'draft', terms text, document_url text, created_by uuid, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists koja_global_business_approvals (
  id uuid primary key default gen_random_uuid(), business_id uuid not null, entity_type text not null, entity_id uuid not null, requested_by uuid not null, approved_by uuid, status text not null default 'pending', note text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists koja_global_business_analytics (
  id uuid primary key default gen_random_uuid(), business_id uuid not null, metric_date date not null default current_date, currency text not null default 'ZMW', revenue numeric(18,2) not null default 0, expenses numeric(18,2) not null default 0, b2b_gross numeric(18,2) not null default 0, b2b_orders integer not null default 0, customers integer not null default 0, suppliers integer not null default 0, employees integer not null default 0, open_disputes integer not null default 0, pending_payouts numeric(18,2) not null default 0, created_at timestamptz not null default now(), unique(business_id,metric_date)
);

create index if not exists idx_koja_global_settings_country on koja_global_business_settings(country_code);
create index if not exists idx_koja_global_roles_business on koja_global_business_roles(business_id,status);
create index if not exists idx_koja_global_contracts_business on koja_global_business_contracts(business_id,created_at desc);
create index if not exists idx_koja_global_approvals_business on koja_global_business_approvals(business_id,status,created_at desc);
create index if not exists idx_koja_global_analytics_business on koja_global_business_analytics(business_id,metric_date desc);

alter table koja_global_business_settings enable row level security;
alter table koja_global_business_roles enable row level security;
alter table koja_global_business_contracts enable row level security;
alter table koja_global_business_approvals enable row level security;
alter table koja_global_business_analytics enable row level security;


-- KOJA Media V6: additive-only migration. No tables are dropped or recreated.
alter table public.koja_public_posts add column if not exists media_processing_status text default 'pending';
alter table public.koja_public_posts add column if not exists media_master_url text;
alter table public.koja_public_posts add column if not exists media_duration_seconds numeric;
alter table public.koja_public_posts add column if not exists media_source_width integer;
alter table public.koja_public_posts add column if not exists media_source_height integer;
alter table public.koja_public_posts add column if not exists media_processed_at timestamptz;
alter table public.koja_public_posts add column if not exists media_processing_error text;
alter table public.koja_public_posts add column if not exists media_subtitles_url text;

create index if not exists koja_public_posts_media_processing_idx
on public.koja_public_posts(media_type, media_processing_status, created_at desc);

create table if not exists public.koja_media_watch_progress (
 id uuid primary key default gen_random_uuid(),
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 user_id uuid not null,
 session_id text,
 position_seconds numeric not null default 0,
 duration_seconds numeric not null default 0,
 updated_at timestamptz default now(),
 unique(post_id,user_id)
);
create index if not exists koja_media_watch_progress_user_idx
on public.koja_media_watch_progress(user_id, updated_at desc);
create index if not exists koja_media_watch_progress_post_idx
on public.koja_media_watch_progress(post_id, updated_at desc);

-- Optional subtitles are stored as a WebVTT public URL in media_subtitles_url.
-- The HLS worker creates media_master_url after successful processing.


-- KOJA Media external live URL registry
create table if not exists public.koja_media_live_streams (
 id uuid primary key default gen_random_uuid(),
 owner_id uuid references auth.users(id) on delete set null,
 title text not null,
 stream_url text not null,
 provider text not null default 'other',
 thumbnail_url text,
 category text,
 is_public boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_media_live_streams_created_idx on public.koja_media_live_streams(created_at desc);
create index if not exists koja_media_live_streams_public_idx on public.koja_media_live_streams(is_public,created_at desc);
