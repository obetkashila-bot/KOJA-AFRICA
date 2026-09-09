-- KOJA V10 SCALE ARCHITECTURE — safe/idempotent
-- Adds monetization infrastructure only. Does not alter Communications.
create table if not exists public.koja_countries (
 id uuid primary key default gen_random_uuid(), country_code text not null unique,
 name text not null, currency text not null, currency_symbol text default '', active boolean not null default true,
 platform_fee_rate numeric(8,5) default 0.10, delivery_fee_rate numeric(8,5) default 0.10,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
insert into public.koja_countries(country_code,name,currency,currency_symbol,platform_fee_rate) values
('ZM','Zambia','ZMW','K',0.10),('CD','DR Congo','CDF','FC',0.10),('MW','Malawi','MWK','MK',0.10),('TZ','Tanzania','TZS','TSh',0.10),('ZW','Zimbabwe','USD','$',0.10),('BW','Botswana','BWP','P',0.10),('ZA','South Africa','ZAR','R',0.08),('KE','Kenya','KES','KSh',0.10),('UG','Uganda','UGX','USh',0.10),('RW','Rwanda','RWF','RF',0.10),('NG','Nigeria','NGN','₦',0.08),('GH','Ghana','GHS','GH₵',0.10)
on conflict(country_code) do update set name=excluded.name,currency=excluded.currency,currency_symbol=excluded.currency_symbol,platform_fee_rate=excluded.platform_fee_rate,updated_at=now();

create table if not exists public.koja_api_keys (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, name text not null,
 key_prefix text not null, key_hash text not null unique, scopes jsonb not null default '[]'::jsonb,
 monthly_quota bigint not null default 10000, requests_used bigint not null default 0,
 status text not null default 'active', last_used_at timestamptz, created_at timestamptz not null default now()
);
create index if not exists koja_api_keys_user_idx on public.koja_api_keys(user_id,status);

create table if not exists public.koja_api_usage_events (
 id uuid primary key default gen_random_uuid(), api_key_id uuid, user_id uuid, endpoint text not null,
 units numeric(14,4) not null default 1, amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW', created_at timestamptz not null default now()
);
create index if not exists koja_api_usage_events_date_idx on public.koja_api_usage_events(created_at desc);

create table if not exists public.koja_ad_events (
 id uuid primary key default gen_random_uuid(), campaign_id uuid, user_id uuid, event_type text not null,
 amount numeric(14,4) not null default 0, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists koja_ad_events_campaign_idx on public.koja_ad_events(campaign_id,created_at desc);

create table if not exists public.koja_procurement_quotes (
 id uuid primary key default gen_random_uuid(), request_id uuid not null, supplier_id uuid not null,
 unit_price numeric(14,2) not null default 0, quantity numeric(14,2) not null default 1,
 delivery_fee numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0,
 status text not null default 'submitted', note text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_procurement_quotes_request_idx on public.koja_procurement_quotes(request_id,created_at desc);

create table if not exists public.koja_affiliate_events (
 id uuid primary key default gen_random_uuid(), referrer_id uuid, referred_user_id uuid, order_id uuid,
 amount numeric(14,2) not null default 0, commission numeric(14,2) not null default 0,
 status text not null default 'pending', created_at timestamptz not null default now()
);
create index if not exists koja_affiliate_events_referrer_idx on public.koja_affiliate_events(referrer_id,created_at desc);

alter table if exists public.koja_market_orders add column if not exists currency text default 'ZMW';
alter table if exists public.koja_market_orders add column if not exists platform_fee numeric(14,2) default 0;
alter table if exists public.koja_market_orders add column if not exists driver_fee numeric(14,2) default 0;
alter table if exists public.koja_market_orders add column if not exists country_code text default 'ZM';
