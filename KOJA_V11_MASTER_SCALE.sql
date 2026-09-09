-- KOJA V11 MASTER AFRICA SCALE — safe/idempotent migration
-- Does not modify Communications/WebRTC/FCM/LiveKit.
create extension if not exists pgcrypto;

create table if not exists public.koja_countries (id uuid primary key default gen_random_uuid(), country_code text unique not null, country_name text not null, currency text not null, currency_symbol text not null default '', active boolean not null default true, platform_fee_rate numeric(8,5) not null default 0.10, delivery_fee_rate numeric(8,5) not null default 0.10, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
insert into public.koja_countries(country_code,country_name,currency,currency_symbol) values ('ZM','Zambia','ZMW','K'),('CD','DR Congo','CDF','FC'),('MW','Malawi','MWK','MK'),('TZ','Tanzania','TZS','TSh'),('ZW','Zimbabwe','USD','$'),('BW','Botswana','BWP','P'),('ZA','South Africa','ZAR','R'),('KE','Kenya','KES','KSh'),('UG','Uganda','UGX','USh'),('RW','Rwanda','RWF','RF'),('NG','Nigeria','NGN','₦'),('GH','Ghana','GHS','GH₵') on conflict(country_code) do update set country_name=excluded.country_name,currency=excluded.currency,currency_symbol=excluded.currency_symbol,updated_at=now();

create table if not exists public.koja_api_keys (id uuid primary key default gen_random_uuid(), user_id uuid not null, name text not null default 'KOJA API Key', key_prefix text not null, key_hash text not null unique, scopes jsonb not null default '[]'::jsonb, monthly_quota integer not null default 10000, requests_used integer not null default 0, status text not null default 'active', last_used_at timestamptz, created_at timestamptz not null default now());
create index if not exists koja_api_keys_user_idx on public.koja_api_keys(user_id,status);
create table if not exists public.koja_api_usage_events (id uuid primary key default gen_random_uuid(), api_key_id uuid references public.koja_api_keys(id) on delete cascade, user_id uuid, endpoint text not null, units integer not null default 1, amount numeric(14,2) not null default 0, currency text not null default 'ZMW', created_at timestamptz not null default now());
create index if not exists koja_api_usage_events_created_idx on public.koja_api_usage_events(created_at desc);
create table if not exists public.koja_ad_events (id uuid primary key default gen_random_uuid(), campaign_id uuid, user_id uuid, event_type text not null, amount numeric(14,2) not null default 0, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now());
create index if not exists koja_ad_events_campaign_idx on public.koja_ad_events(campaign_id,created_at desc);
create table if not exists public.koja_procurement_quotes (id uuid primary key default gen_random_uuid(), request_id uuid, supplier_id uuid, unit_price numeric(14,2) not null default 0, quantity integer not null default 1, delivery_fee numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0, status text not null default 'submitted', note text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create index if not exists koja_procurement_quotes_request_idx on public.koja_procurement_quotes(request_id,status);
create table if not exists public.koja_affiliate_events (id uuid primary key default gen_random_uuid(), referrer_id uuid, referred_user_id uuid, order_id uuid, amount numeric(14,2) not null default 0, commission numeric(14,2) not null default 0, status text not null default 'pending', created_at timestamptz not null default now());
create index if not exists koja_affiliate_events_referrer_idx on public.koja_affiliate_events(referrer_id,created_at desc);

alter table if exists public.koja_revenue_payments add column if not exists currency text default 'ZMW';
alter table if exists public.koja_revenue_payments add column if not exists user_id uuid;
alter table if exists public.koja_revenue_payments add column if not exists plan text;
alter table if exists public.koja_revenue_payments add column if not exists reference text;
alter table if exists public.koja_ad_campaigns add column if not exists user_id uuid;
alter table if exists public.koja_ad_campaigns add column if not exists name text;
alter table if exists public.koja_ad_campaigns add column if not exists budget numeric(14,2) default 0;
alter table if exists public.koja_ad_campaigns add column if not exists currency text default 'ZMW';
alter table if exists public.koja_ad_campaigns add column if not exists status text default 'pending';
alter table if exists public.koja_procurement_requests add column if not exists buyer_id uuid;
alter table if exists public.koja_procurement_requests add column if not exists title text;
alter table if exists public.koja_procurement_requests add column if not exists description text;
alter table if exists public.koja_procurement_requests add column if not exists quantity integer default 1;
alter table if exists public.koja_procurement_requests add column if not exists status text default 'open';
alter table if exists public.koja_enterprise_accounts add column if not exists user_id uuid;
alter table if exists public.koja_enterprise_accounts add column if not exists organization_name text;
alter table if exists public.koja_enterprise_accounts add column if not exists contact_email text;
alter table if exists public.koja_enterprise_accounts add column if not exists status text default 'lead';
alter table if exists public.koja_market_orders add column if not exists currency text default 'ZMW';
alter table if exists public.koja_market_orders add column if not exists platform_fee numeric(14,2) default 0;
alter table if exists public.koja_market_orders add column if not exists driver_fee numeric(14,2) default 0;
alter table if exists public.koja_market_orders add column if not exists country_code text default 'ZM';
