-- KOJA AFRICA FOUNDATIONS V2 -> FULL MODULE ACTIVATION
-- ADDITIVE / UPDATE-SAFE: no DROP, no table recreation, no data deletion.

create table if not exists public.koja_business_orders (
 id uuid primary key default gen_random_uuid(), business_id uuid, product_id uuid, buyer_id uuid,
 quantity integer not null default 1, item_amount numeric(14,2) not null default 0,
 delivery_fee numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0,
 fulfillment_method text default 'delivery', delivery_address text, recipient_phone text,
 payment_reference text, payment_transaction_id text, status text not null default 'pending', currency text not null default 'ZMW',
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create unique index if not exists koja_business_orders_payment_ref_uq on public.koja_business_orders(payment_reference) where payment_reference is not null;
create index if not exists koja_business_orders_buyer_idx on public.koja_business_orders(buyer_id,created_at desc);
create index if not exists koja_business_orders_business_idx on public.koja_business_orders(business_id,created_at desc);

create table if not exists public.koja_ai_memories (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, memory_key text not null,
 memory_value text not null, source text default 'explicit_user', confidence numeric(4,3) default 1.0,
 is_active boolean default true, created_at timestamptz default now(), updated_at timestamptz default now(),
 unique(user_id,memory_key)
);
create index if not exists koja_ai_memories_user_idx on public.koja_ai_memories(user_id,is_active,updated_at desc);

create table if not exists public.koja_push_subscriptions (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, endpoint text not null,
 subscription jsonb not null default '{}'::jsonb, user_agent text, created_at timestamptz default now(), updated_at timestamptz default now(),
 unique(user_id,endpoint)
);
create index if not exists koja_push_subscriptions_user_idx on public.koja_push_subscriptions(user_id,created_at desc);

-- V13 Ads
create table if not exists public.koja_v13_ad_campaigns (
 id uuid primary key default gen_random_uuid(), advertiser_id uuid not null, title text not null default '',
 placement text default 'market', target_url text, budget numeric(14,2) default 0, spent numeric(14,2) default 0,
 starts_at timestamptz, ends_at timestamptz, status text default 'draft', metadata jsonb default '{}'::jsonb,
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_v13_ad_events (
 id uuid primary key default gen_random_uuid(), campaign_id uuid, user_id uuid, event_type text not null,
 amount numeric(14,4) default 0, metadata jsonb default '{}'::jsonb, created_at timestamptz default now()
);
create index if not exists koja_v13_campaign_owner_idx on public.koja_v13_ad_campaigns(advertiser_id,created_at desc);
create index if not exists koja_v13_events_campaign_idx on public.koja_v13_ad_events(campaign_id,created_at desc);

-- V14 Pay orchestration
create table if not exists public.koja_v14_payment_intents (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW', provider text default 'flutterwave', reference text unique,
 status text not null default 'created', purpose text, target_id text, metadata jsonb default '{}'::jsonb,
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_v14_payment_user_idx on public.koja_v14_payment_intents(user_id,created_at desc);

-- V16 Intelligence
create table if not exists public.koja_v16_intelligence_events (
 id uuid primary key default gen_random_uuid(), user_id uuid, service_key text, event_type text not null,
 object_id text, value numeric(18,6), metadata jsonb default '{}'::jsonb, created_at timestamptz default now()
);
create index if not exists koja_v16_events_idx on public.koja_v16_intelligence_events(service_key,event_type,created_at desc);

-- V17 Identity & Trust
create table if not exists public.koja_v17_identity (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, identity_type text default 'account',
 document_type text, document_reference text, status text default 'pending', verification_level integer default 0,
 metadata jsonb default '{}'::jsonb, created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_v17_identity_user_idx on public.koja_v17_identity(user_id,created_at desc);

-- Shared engine event/revenue layers
create table if not exists public.koja_engine_events (
 id uuid primary key default gen_random_uuid(), user_id uuid, engine text not null, action text not null,
 metadata jsonb default '{}'::jsonb, created_at timestamptz default now()
);
create index if not exists koja_engine_events_idx on public.koja_engine_events(engine,created_at desc);
create table if not exists public.koja_engine_revenue (
 id uuid primary key default gen_random_uuid(), service_key text not null, revenue_type text not null,
 amount numeric(14,2) not null default 0, currency text default 'ZMW', reference_id text,
 metadata jsonb default '{}'::jsonb, created_at timestamptz default now()
);
create index if not exists koja_engine_revenue_idx on public.koja_engine_revenue(service_key,created_at desc);
create table if not exists public.koja_user_service_events (
 id uuid primary key default gen_random_uuid(), user_id uuid, service_key text not null, event_type text not null,
 object_id text, country_code text default 'ZM', metadata jsonb default '{}'::jsonb, created_at timestamptz default now()
);
create index if not exists koja_user_service_events_idx on public.koja_user_service_events(user_id,service_key,created_at desc);

-- V15 Cloud & Developer
create table if not exists public.koja_api_keys (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, name text not null default 'KOJA API Key',
 key_prefix text, key_hash text, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now(), revoked_at timestamptz
);
create table if not exists public.koja_api_usage (
 id uuid primary key default gen_random_uuid(), user_id uuid, api_key_id uuid, endpoint text, units numeric(14,4) default 1,
 metadata jsonb default '{}'::jsonb, created_at timestamptz default now()
);
create index if not exists koja_api_usage_user_idx on public.koja_api_usage(user_id,created_at desc);

-- V18 Workspace & Enterprise
create table if not exists public.koja_workspaces (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null, description text default '',
 status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_workspace_members (
 workspace_id uuid not null, user_id uuid not null, role text default 'member', status text default 'active', joined_at timestamptz default now(),
 primary key(workspace_id,user_id)
);
create table if not exists public.koja_workspace_files (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null, owner_id uuid, name text, file_url text,
 mime_type text, size_bytes bigint default 0, created_at timestamptz default now()
);
create table if not exists public.koja_workspace_documents (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null, owner_id uuid, title text, body text default '',
 status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_contracts (
 id uuid primary key default gen_random_uuid(), owner_id uuid, workspace_id uuid, name text, status text default 'draft',
 value numeric(14,2) default 0, currency text default 'ZMW', starts_at timestamptz, ends_at timestamptz, metadata jsonb default '{}'::jsonb,
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_seats (
 id uuid primary key default gen_random_uuid(), contract_id uuid, workspace_id uuid, user_id uuid, role text default 'member', status text default 'active', created_at timestamptz default now()
);
create index if not exists koja_workspace_owner_idx on public.koja_workspaces(owner_id,created_at desc);
create index if not exists koja_workspace_members_user_idx on public.koja_workspace_members(user_id,workspace_id);

-- V19 Ecosystem
create table if not exists public.koja_service_registry (
 id uuid primary key default gen_random_uuid(), service_key text unique not null, name text not null, description text default '',
 status text default 'active', url text, metadata jsonb default '{}'::jsonb, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_ecosystem_links (
 id uuid primary key default gen_random_uuid(), user_id uuid, from_service text, to_service text, relation text default 'connected',
 object_id text, metadata jsonb default '{}'::jsonb, created_at timestamptz default now()
);
create table if not exists public.koja_unified_transactions (
 id uuid primary key default gen_random_uuid(), user_id uuid, source_service text, target_service text, reference text,
 amount numeric(14,2) default 0, currency text default 'ZMW', status text default 'pending', metadata jsonb default '{}'::jsonb,
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_unified_transactions_user_idx on public.koja_unified_transactions(user_id,created_at desc);

-- V20 Autonomous Africa
create table if not exists public.koja_ai_agents (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null, goal text default '',
 status text default 'draft', config jsonb default '{}'::jsonb, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_ai_agent_runs (
 id uuid primary key default gen_random_uuid(), agent_id uuid not null, owner_id uuid, status text default 'queued',
 input jsonb default '{}'::jsonb, output jsonb default '{}'::jsonb, error text, started_at timestamptz, completed_at timestamptz, created_at timestamptz default now()
);
create table if not exists public.koja_iot_devices (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null, device_type text default 'generic',
 device_key text, status text default 'offline', metadata jsonb default '{}'::jsonb, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_iot_telemetry (
 id uuid primary key default gen_random_uuid(), device_id uuid not null, owner_id uuid, metric text not null, value numeric(18,6),
 unit text, metadata jsonb default '{}'::jsonb, created_at timestamptz default now()
);
create table if not exists public.koja_autonomy_jobs (
 id uuid primary key default gen_random_uuid(), owner_id uuid, agent_id uuid, job_type text not null, status text default 'queued',
 payload jsonb default '{}'::jsonb, result jsonb default '{}'::jsonb, scheduled_at timestamptz, completed_at timestamptz, created_at timestamptz default now()
);
create table if not exists public.koja_future_infrastructure (
 id uuid primary key default gen_random_uuid(), owner_id uuid, category text not null, name text not null, status text default 'planned',
 metadata jsonb default '{}'::jsonb, created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_agents_owner_idx on public.koja_ai_agents(owner_id,created_at desc);
create index if not exists koja_devices_owner_idx on public.koja_iot_devices(owner_id,created_at desc);
create index if not exists koja_telemetry_device_idx on public.koja_iot_telemetry(device_id,created_at desc);

-- Safe additive columns for tables that may already exist in older KOJA deployments.
alter table if exists public.koja_ai_conversations add column if not exists updated_at timestamptz default now();
alter table if exists public.koja_ai_conversations add column if not exists is_archived boolean default false;
alter table if exists public.koja_ai_messages add column if not exists created_at timestamptz default now();
alter table if exists public.koja_business_orders add column if not exists payment_transaction_id text;
alter table if exists public.koja_push_subscriptions add column if not exists user_agent text;

-- Register the core engines idempotently.
insert into public.koja_service_registry(service_key,name,description,status)
values
('discover','KOJA Discover','Search and discovery across KOJA services','active'),
('ads','KOJA Ads','Advertising campaigns, placements and events','active'),
('pay','KOJA Pay','Payment intents and unified payment orchestration','active'),
('cloud','KOJA Cloud','API identity, usage and developer infrastructure','active'),
('intelligence','KOJA Intelligence','Cross-service analytics and intelligence events','active'),
('identity','KOJA Identity','Identity, verification and trust controls','active'),
('workspace','KOJA Workspace','Documents, files, teams and enterprise workspaces','active'),
('ecosystem','KOJA Ecosystem','Unified service links and transactions','active'),
('autonomous_ai','KOJA Autonomous AI','Agents, automation, IoT and future infrastructure','active')
on conflict(service_key) do update set name=excluded.name,description=excluded.description,status='active',updated_at=now();
