-- KOJA V12-V17 AFRICA ENGINE SUITE
-- Safe/idempotent additive migration. Does not alter Communications.

-- V12 Search / discovery indexes
create index if not exists koja_market_products_search_idx on public.koja_market_products (created_at desc);
create index if not exists koja_businesses_search_idx on public.koja_businesses (created_at desc);
create index if not exists service_providers_search_idx on public.service_providers (created_at desc);

-- V13 Ads Network
create table if not exists public.koja_v13_ad_campaigns (
 id uuid primary key default gen_random_uuid(), advertiser_id uuid not null, name text not null,
 placement text not null default 'search', daily_budget numeric(18,2) not null default 0,
 total_budget numeric(18,2) not null default 0, status text not null default 'draft',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_v13_ads_advertiser_idx on public.koja_v13_ad_campaigns(advertiser_id,created_at desc);
create table if not exists public.koja_v13_ad_events (
 id uuid primary key default gen_random_uuid(), campaign_id uuid not null, user_id uuid,
 event_type text not null default 'impression', metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
create index if not exists koja_v13_ad_events_campaign_idx on public.koja_v13_ad_events(campaign_id,created_at desc);

-- V14 Pay orchestration layer. Existing Flutterwave flows remain untouched.
create table if not exists public.koja_v14_payment_intents (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, amount numeric(18,2) not null check(amount>0),
 currency text not null default 'ZMW', purpose text not null, provider text not null default 'flutterwave',
 status text not null default 'pending', provider_reference text, metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_v14_pay_user_idx on public.koja_v14_payment_intents(user_id,created_at desc);

-- V15 Cloud / Developer
alter table if exists public.koja_api_keys add column if not exists name text default 'KOJA API Key';
alter table if exists public.koja_api_keys add column if not exists key_prefix text default '';
alter table if exists public.koja_api_keys add column if not exists status text default 'active';
alter table if exists public.koja_api_keys add column if not exists updated_at timestamptz default now();
alter table if exists public.koja_api_usage_events add column if not exists units integer default 1;

-- V16 Data & Intelligence
create table if not exists public.koja_v16_intelligence_events (
 id uuid primary key default gen_random_uuid(), source text not null, metric text not null,
 country_code text default 'ZM', value numeric(24,6) default 0, metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
create index if not exists koja_v16_intel_metric_idx on public.koja_v16_intelligence_events(metric,country_code,created_at desc);

-- V17 Identity & Trust
create table if not exists public.koja_v17_identity (
 id uuid primary key default gen_random_uuid(), user_id uuid not null unique, legal_name text not null default '',
 document_type text default '', document_number text default '', status text not null default 'unverified',
 verification_level text not null default 'basic', admin_note text default '',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_v17_identity_status_idx on public.koja_v17_identity(status,created_at desc);

-- Unified engine audit log
create table if not exists public.koja_engine_events (
 id uuid primary key default gen_random_uuid(), user_id uuid, engine text not null, action text not null,
 metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists koja_engine_events_engine_idx on public.koja_engine_events(engine,created_at desc);
