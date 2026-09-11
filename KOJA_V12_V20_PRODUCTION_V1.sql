-- KOJA AFRICA Production Hardening V2
-- SAFE / ADDITIVE / IDEMPOTENT. Does not drop, recreate, truncate or delete existing business data.

create extension if not exists pgcrypto;

create table if not exists public.koja_idempotency_keys_v2 (
  id uuid primary key default gen_random_uuid(),
  idempotency_key text not null,
  scope text not null,
  user_id uuid,
  request_hash text not null default '',
  status text not null default 'processing',
  response_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (idempotency_key, scope)
);
create index if not exists koja_idempotency_user_idx on public.koja_idempotency_keys_v2(user_id, created_at desc);
create index if not exists koja_idempotency_status_idx on public.koja_idempotency_keys_v2(status, updated_at desc);

alter table if exists public.koja_market_payouts add column if not exists processed_at timestamptz;
alter table if exists public.koja_market_payouts add column if not exists failure_reason text;

alter table if exists public.deliveries add column if not exists rejection_count integer not null default 0;
alter table if exists public.deliveries add column if not exists last_reassigned_at timestamptz;

-- Keep the audit table usable for the hardening layer even when an earlier migration created it.
alter table if exists public.koja_audit_log_v2 add column if not exists metadata jsonb not null default '{}'::jsonb;
alter table if exists public.koja_audit_log_v2 add column if not exists created_at timestamptz not null default now();

-- Cleanup helper for stale idempotency records. Safe to run manually or from a scheduled job.
create or replace function public.koja_cleanup_idempotency_v2(retention_days integer default 7)
returns integer
language plpgsql
security definer
as $$
declare
  deleted_count integer;
begin
  delete from public.koja_idempotency_keys_v2
  where created_at < now() - make_interval(days => greatest(retention_days, 1));
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

-- Verification
select 'koja_idempotency_keys_v2' as table_name, to_regclass('public.koja_idempotency_keys_v2') is not null as installed
union all
select 'koja_market_payouts.processed_at', exists(select 1 from information_schema.columns where table_schema='public' and table_name='koja_market_payouts' and column_name='processed_at')
union all
select 'deliveries.rejection_count', exists(select 1 from information_schema.columns where table_schema='public' and table_name='deliveries' and column_name='rejection_count')
union all
select 'koja_audit_log_v2.metadata', exists(select 1 from information_schema.columns where table_schema='public' and table_name='koja_audit_log_v2' and column_name='metadata');
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

-- ============================================================
-- KOJA V18 -> V20 ALL-IN-ONE EXTENSION
-- V18 Workspace + Enterprise
-- V19 Africa Super-App / Ecosystem Integration
-- V20 Autonomous Africa / Future Infrastructure
-- Safe/idempotent migration: CREATE IF NOT EXISTS / ADD IF NOT EXISTS
-- ============================================================

-- =========================
-- V18: WORKSPACE + ENTERPRISE
-- =========================
create table if not exists public.koja_workspaces (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  name text not null,
  workspace_type text not null default 'business',
  plan text not null default 'free',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_workspaces_owner_idx on public.koja_workspaces(owner_id,created_at desc);

create table if not exists public.koja_workspace_members (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.koja_workspaces(id) on delete cascade,
  user_id uuid not null,
  role text not null default 'member',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  unique(workspace_id,user_id)
);
create index if not exists koja_workspace_members_user_idx on public.koja_workspace_members(user_id,created_at desc);

create table if not exists public.koja_workspace_files (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.koja_workspaces(id) on delete cascade,
  owner_id uuid not null,
  name text not null,
  storage_path text,
  mime_type text,
  size_bytes bigint default 0,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_workspace_files_ws_idx on public.koja_workspace_files(workspace_id,created_at desc);

create table if not exists public.koja_workspace_documents (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.koja_workspaces(id) on delete cascade,
  owner_id uuid not null,
  title text not null,
  content text default '',
  document_type text not null default 'document',
  version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_workspace_documents_ws_idx on public.koja_workspace_documents(workspace_id,updated_at desc);

create table if not exists public.koja_enterprise_contracts (
  id uuid primary key default gen_random_uuid(),
  account_id uuid,
  customer_id uuid,
  contract_name text not null,
  plan text not null default 'enterprise',
  value numeric(18,2) not null default 0,
  currency text not null default 'USD',
  status text not null default 'lead',
  starts_at timestamptz,
  ends_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_enterprise_contracts_status_idx on public.koja_enterprise_contracts(status,created_at desc);

create table if not exists public.koja_enterprise_seats (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.koja_enterprise_contracts(id) on delete cascade,
  user_id uuid,
  seat_role text not null default 'user',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  unique(contract_id,user_id)
);

-- =========================
-- V19: SUPER-APP / ECOSYSTEM
-- =========================
create table if not exists public.koja_service_registry (
  id uuid primary key default gen_random_uuid(),
  service_key text not null unique,
  service_name text not null,
  category text not null,
  version text not null default '1.0',
  status text not null default 'active',
  api_base text,
  revenue_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.koja_service_registry(service_key,service_name,category) values
('search','KOJA Search','discovery'),
('ads','KOJA Ads','advertising'),
('pay','KOJA Pay','payments'),
('cloud','KOJA Cloud','infrastructure'),
('developer','KOJA Developer','developer'),
('data','KOJA Data Intelligence','analytics'),
('identity','KOJA Identity','trust'),
('workspace','KOJA Workspace','productivity'),
('enterprise','KOJA Enterprise','business'),
('market','KOJA Market','commerce'),
('logistics','KOJA Logistics','logistics'),
('ai','KOJA AI','artificial_intelligence')
on conflict(service_key) do nothing;

create table if not exists public.koja_user_service_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  service_key text not null,
  event_type text not null,
  object_id text,
  country_code text default 'ZM',
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists koja_user_service_events_user_idx on public.koja_user_service_events(user_id,created_at desc);
create index if not exists koja_user_service_events_service_idx on public.koja_user_service_events(service_key,created_at desc);

create table if not exists public.koja_ecosystem_links (
  id uuid primary key default gen_random_uuid(),
  source_service text not null,
  target_service text not null,
  link_type text not null default 'related',
  enabled boolean not null default true,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(source_service,target_service,link_type)
);

create table if not exists public.koja_unified_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  service_key text not null,
  external_reference text,
  amount numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  platform_fee numeric(18,2) not null default 0,
  status text not null default 'pending',
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_unified_transactions_user_idx on public.koja_unified_transactions(user_id,created_at desc);
create index if not exists koja_unified_transactions_service_idx on public.koja_unified_transactions(service_key,status,created_at desc);

-- =========================
-- V20: AUTONOMOUS AFRICA / FUTURE INFRASTRUCTURE
-- =========================
create table if not exists public.koja_ai_agents (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid,
  name text not null,
  agent_type text not null default 'general',
  status text not null default 'active',
  instructions text default '',
  tools jsonb not null default '[]'::jsonb,
  spending_limit numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_ai_agents_owner_idx on public.koja_ai_agents(owner_id,created_at desc);

create table if not exists public.koja_ai_agent_runs (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references public.koja_ai_agents(id) on delete cascade,
  owner_id uuid,
  task text not null,
  status text not null default 'queued',
  result jsonb default '{}'::jsonb,
  cost numeric(18,6) not null default 0,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);
create index if not exists koja_ai_agent_runs_agent_idx on public.koja_ai_agent_runs(agent_id,created_at desc);

create table if not exists public.koja_iot_devices (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid,
  device_key text not null unique,
  device_type text not null,
  name text not null,
  country_code text default 'ZM',
  latitude numeric(10,7),
  longitude numeric(10,7),
  status text not null default 'offline',
  metadata jsonb default '{}'::jsonb,
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_iot_devices_owner_idx on public.koja_iot_devices(owner_id,created_at desc);

create table if not exists public.koja_iot_telemetry (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references public.koja_iot_devices(id) on delete cascade,
  metric text not null,
  value numeric,
  unit text,
  payload jsonb default '{}'::jsonb,
  recorded_at timestamptz not null default now()
);
create index if not exists koja_iot_telemetry_device_idx on public.koja_iot_telemetry(device_id,recorded_at desc);

create table if not exists public.koja_autonomy_jobs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid,
  job_type text not null,
  status text not null default 'queued',
  priority integer not null default 100,
  input jsonb default '{}'::jsonb,
  output jsonb default '{}'::jsonb,
  estimated_cost numeric(18,6) not null default 0,
  actual_cost numeric(18,6) not null default 0,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz
);
create index if not exists koja_autonomy_jobs_status_idx on public.koja_autonomy_jobs(status,priority,created_at);

create table if not exists public.koja_future_infrastructure (
  id uuid primary key default gen_random_uuid(),
  asset_type text not null,
  asset_name text not null,
  country_code text default 'ZM',
  status text not null default 'planned',
  latitude numeric(10,7),
  longitude numeric(10,7),
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_future_infrastructure_country_idx on public.koja_future_infrastructure(country_code,asset_type,status);

-- Common platform metadata
alter table if exists public.profiles add column if not exists koja_id text;
alter table if exists public.profiles add column if not exists verification_level text default 'basic';
alter table if exists public.profiles add column if not exists default_country_code text default 'ZM';
create unique index if not exists profiles_koja_id_unique_idx on public.profiles(koja_id) where koja_id is not null;

-- V20 revenue/event foundation
create table if not exists public.koja_engine_revenue (
  id uuid primary key default gen_random_uuid(),
  service_key text not null,
  revenue_type text not null,
  amount numeric(18,2) not null default 0,
  currency text not null default 'USD',
  reference_id text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists koja_engine_revenue_service_idx on public.koja_engine_revenue(service_key,created_at desc);

-- ============================================================
-- END KOJA V12 -> V20 ALL-IN-ONE
-- ============================================================

-- ============================================================
-- KOJA CORE NAMED ENGINES + SECURITY UPGRADE
-- Existing tables are upgraded in place. No drops/recreates/truncates.
-- Communications is intentionally untouched.
-- ============================================================

alter table if exists public.koja_api_keys add column if not exists key_hash text;
alter table if exists public.koja_api_keys add column if not exists scopes jsonb not null default '[]'::jsonb;
alter table if exists public.koja_api_keys add column if not exists expires_at timestamptz;
alter table if exists public.koja_api_keys add column if not exists last_used_at timestamptz;
alter table if exists public.koja_api_keys add column if not exists revoked_at timestamptz;
create unique index if not exists koja_api_keys_hash_uidx on public.koja_api_keys(key_hash) where key_hash is not null;
create index if not exists koja_api_keys_user_status_idx on public.koja_api_keys(user_id,status,created_at desc);

-- Production service names. Existing registry rows are upgraded, not duplicated.
update public.koja_service_registry set service_name='KOJA Discover' where service_key='search';
update public.koja_service_registry set service_name='KOJA Ads' where service_key='ads';
update public.koja_service_registry set service_name='KOJA Pay' where service_key='pay';
update public.koja_service_registry set service_name='KOJA Cloud' where service_key in ('cloud','developer');
update public.koja_service_registry set service_name='KOJA Intelligence' where service_key='data';
update public.koja_service_registry set service_name='KOJA Identity' where service_key='identity';
update public.koja_service_registry set service_name='KOJA Workspace' where service_key='workspace';
update public.koja_service_registry set service_name='KOJA Ecosystem' where service_key='enterprise';
update public.koja_service_registry set service_name='KOJA Market' where service_key='market';
update public.koja_service_registry set service_name='KOJA Logistics' where service_key='logistics';
update public.koja_service_registry set service_name='KOJA AI' where service_key='ai';

-- Named-engine registry: this is the production attachment map.
create table if not exists public.koja_core_engine_registry (
 id uuid primary key default gen_random_uuid(),
 engine_key text not null unique,
 engine_name text not null,
 category text not null,
 attached_services jsonb not null default '[]'::jsonb,
 status text not null default 'active',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);

insert into public.koja_core_engine_registry(engine_key,engine_name,category,attached_services) values
('discover','KOJA Discover','discovery','["market","business","research","services"]'),
('ads','KOJA Ads','advertising','["market","business","discover","pay"]'),
('pay','KOJA Pay','payments','["market","business","deliveries","ads"]'),
('cloud','KOJA Cloud','infrastructure','["developer","api","security"]'),
('intelligence','KOJA Intelligence','analytics','["ai","business","market","pay","logistics"]'),
('identity','KOJA Identity','trust','["auth","profiles","security","business"]'),
('workspace','KOJA Workspace','productivity','["business","documents","research","enterprise"]'),
('ecosystem','KOJA Ecosystem','platform','["discover","market","business","logistics","ai","pay"]'),
('autonomous_ai','KOJA Autonomous AI','artificial_intelligence','["ai","intelligence","identity","cloud","ecosystem"]')
on conflict(engine_key) do update set engine_name=excluded.engine_name,category=excluded.category,attached_services=excluded.attached_services,updated_at=now();

create index if not exists koja_core_engine_registry_status_idx on public.koja_core_engine_registry(status,engine_name);

select engine_key,engine_name,status from public.koja_core_engine_registry order by engine_name;

-- KOJA Notification Center / Push (additive, safe)
create table if not exists public.koja_notification_preferences (
 user_id uuid primary key, push_enabled boolean default true, sound_enabled boolean default true,
 market_enabled boolean default true, delivery_enabled boolean default true, ai_enabled boolean default true,
 messages_enabled boolean default true, system_enabled boolean default true, updated_at timestamptz default now()
);
create table if not exists public.koja_push_subscriptions (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, endpoint text not null,
 subscription jsonb not null default '{}'::jsonb, user_agent text, created_at timestamptz default now(),
 updated_at timestamptz default now(), unique(user_id,endpoint)
);
create index if not exists koja_push_subscriptions_user_idx on public.koja_push_subscriptions(user_id,created_at desc);
