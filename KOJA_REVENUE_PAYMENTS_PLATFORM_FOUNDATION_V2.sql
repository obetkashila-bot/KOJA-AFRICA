-- KOJA REVENUE & PAYMENTS V2 -> PLATFORM FOUNDATIONS V2
-- Additive/update-safe bridge. Run after KOJA_PLATFORM_FOUNDATIONS_V2.sql
-- and KOJA_GLOBAL_REVENUE_PAYMENTS_V2.sql when those migrations are installed.
-- No DROP, TRUNCATE, or table recreation.

create extension if not exists pgcrypto;

-- Shared platform event table compatibility.
create table if not exists public.koja_platform_events (
  id uuid primary key default gen_random_uuid(),
  event_key text,
  idempotency_key text,
  user_id uuid,
  organization_id uuid,
  service_key text not null default 'platform',
  event_type text not null,
  entity_type text,
  entity_id text,
  country_code text default 'ZM',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
alter table public.koja_platform_events add column if not exists event_key text;
alter table public.koja_platform_events add column if not exists idempotency_key text;
alter table public.koja_platform_events add column if not exists user_id uuid;
alter table public.koja_platform_events add column if not exists organization_id uuid;
alter table public.koja_platform_events add column if not exists service_key text default 'platform';
alter table public.koja_platform_events add column if not exists event_type text;
alter table public.koja_platform_events add column if not exists entity_type text;
alter table public.koja_platform_events add column if not exists entity_id text;
alter table public.koja_platform_events add column if not exists country_code text default 'ZM';
alter table public.koja_platform_events add column if not exists payload jsonb default '{}'::jsonb;
alter table public.koja_platform_events add column if not exists created_at timestamptz default now();

-- Unified transaction bridge compatibility.
alter table if exists public.koja_unified_transactions add column if not exists organization_id uuid;
alter table if exists public.koja_unified_transactions add column if not exists source_type text;
alter table if exists public.koja_unified_transactions add column if not exists source_id text;
alter table if exists public.koja_unified_transactions add column if not exists payment_provider text;
alter table if exists public.koja_unified_transactions add column if not exists payment_reference text;
alter table if exists public.koja_unified_transactions add column if not exists idempotency_key text;
alter table if exists public.koja_unified_transactions add column if not exists completed_at timestamptz;
alter table if exists public.koja_unified_transactions add column if not exists updated_at timestamptz default now();

-- Existing V20 revenue ledger compatibility.
alter table if exists public.koja_engine_revenue add column if not exists user_id uuid;
alter table if exists public.koja_engine_revenue add column if not exists organization_id uuid;
alter table if exists public.koja_engine_revenue add column if not exists source_type text;
alter table if exists public.koja_engine_revenue add column if not exists source_id text;
alter table if exists public.koja_engine_revenue add column if not exists gross_amount numeric(18,2);
alter table if exists public.koja_engine_revenue add column if not exists seller_amount numeric(18,2);
alter table if exists public.koja_engine_revenue add column if not exists idempotency_key text;
alter table if exists public.koja_engine_revenue add column if not exists transaction_id uuid;
alter table if exists public.koja_engine_revenue add column if not exists updated_at timestamptz default now();

-- Revenue V2 traceability back to the shared foundation.
alter table if exists public.koja_revenue_v2_transactions add column if not exists foundation_transaction_id uuid;
alter table if exists public.koja_revenue_v2_transactions add column if not exists foundation_event_id uuid;
alter table if exists public.koja_revenue_v2_transactions add column if not exists organization_id uuid;
alter table if exists public.koja_revenue_v2_events add column if not exists foundation_event_id uuid;

create index if not exists idx_koja_platform_events_service_created
  on public.koja_platform_events(service_key, created_at desc);
create unique index if not exists idx_koja_platform_events_idempotency
  on public.koja_platform_events(idempotency_key)
  where idempotency_key is not null;
create index if not exists idx_koja_unified_tx_org_created
  on public.koja_unified_transactions(organization_id, created_at desc);
create unique index if not exists idx_koja_unified_tx_idempotency
  on public.koja_unified_transactions(idempotency_key)
  where idempotency_key is not null;
create index if not exists idx_koja_engine_revenue_org_created
  on public.koja_engine_revenue(organization_id, created_at desc);
create unique index if not exists idx_koja_engine_revenue_idempotency
  on public.koja_engine_revenue(idempotency_key)
  where idempotency_key is not null;
create index if not exists idx_koja_revenue_v2_tx_foundation
  on public.koja_revenue_v2_transactions(foundation_transaction_id);
create index if not exists idx_koja_revenue_v2_tx_foundation_event
  on public.koja_revenue_v2_transactions(foundation_event_id);
create index if not exists idx_koja_revenue_v2_events_foundation
  on public.koja_revenue_v2_events(foundation_event_id);

comment on table public.koja_platform_events is 'Shared KOJA platform event stream. Revenue & Payments V2 writes fail-soft, idempotent payment events here.';
