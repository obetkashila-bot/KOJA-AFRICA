-- KOJA PROFIT ENGINE V1
-- SAFE / ADDITIVE: no drops, truncates, or table recreation.

create table if not exists public.koja_profit_orders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  order_type text not null,
  target_id text,
  amount numeric(14,2) not null default 0,
  currency text not null default 'ZMW',
  units integer default 0,
  status text not null default 'pending',
  payment_reference text,
  payment_transaction_id text,
  paid_at timestamptz,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_profit_orders_user_idx on public.koja_profit_orders(user_id,created_at desc);
create index if not exists koja_profit_orders_ref_idx on public.koja_profit_orders(payment_reference);
create index if not exists koja_profit_orders_status_idx on public.koja_profit_orders(status,created_at desc);

create table if not exists public.koja_profit_revenue (
  id uuid primary key default gen_random_uuid(),
  source_type text not null,
  gross_amount numeric(18,2) not null default 0,
  platform_revenue numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  reference_id text,
  user_id uuid,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists koja_profit_revenue_source_idx on public.koja_profit_revenue(source_type,created_at desc);
create index if not exists koja_profit_revenue_ref_idx on public.koja_profit_revenue(reference_id);

create table if not exists public.koja_ai_credit_wallets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique,
  credits integer not null default 0,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index if not exists koja_ai_credit_wallets_user_idx on public.koja_ai_credit_wallets(user_id);

create table if not exists public.koja_ai_credit_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  transaction_type text not null,
  credits integer not null default 0,
  amount numeric(14,2) not null default 0,
  currency text not null default 'ZMW',
  reference_id text,
  created_at timestamptz not null default now()
);
create index if not exists koja_ai_credit_tx_user_idx on public.koja_ai_credit_transactions(user_id,created_at desc);

-- Compatibility additions for the existing V20 revenue foundation.
alter table if exists public.koja_profit_orders add column if not exists metadata jsonb default '{}'::jsonb;
alter table if exists public.koja_profit_revenue add column if not exists metadata jsonb default '{}'::jsonb;

-- Unified profit reporting view.
create or replace view public.koja_profit_summary as
select source_type,
       currency,
       count(*) as revenue_events,
       coalesce(sum(gross_amount),0) as gross_amount,
       coalesce(sum(platform_revenue),0) as platform_revenue
from public.koja_profit_revenue
group by source_type,currency;

-- Optional reporting view for AI-credit sales.
create or replace view public.koja_ai_credit_revenue as
select coalesce(sum(amount),0) as gross_amount,
       count(*) as transactions,
       coalesce(sum(credits),0) as credits_sold
from public.koja_ai_credit_transactions
where transaction_type='purchase';
