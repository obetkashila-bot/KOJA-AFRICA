create table if not exists public.koja_monetization_orders (id uuid primary key default gen_random_uuid(), user_id uuid not null, order_type text not null, target_id uuid, plan text, title text, target_url text, placement text default 'market', days integer, amount numeric(14,2) not null default 0, currency text not null default 'ZMW', status text not null default 'pending', payment_reference text unique, payment_transaction_id text, paid_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create index if not exists koja_mono_orders_user_idx on public.koja_monetization_orders(user_id,created_at desc);
create index if not exists koja_mono_orders_status_idx on public.koja_monetization_orders(status,created_at desc);
create table if not exists public.koja_monetization_ledger (id uuid primary key default gen_random_uuid(), order_id uuid not null references public.koja_monetization_orders(id) on delete cascade, user_id uuid not null, order_type text not null, gross_amount numeric(14,2) not null default 0, platform_revenue numeric(14,2) not null default 0, seller_payout numeric(14,2) not null default 0, currency text not null default 'ZMW', status text not null default 'posted', created_at timestamptz not null default now());
create index if not exists koja_mono_ledger_date_idx on public.koja_monetization_ledger(created_at desc);
create table if not exists public.koja_monetization_events (id uuid primary key default gen_random_uuid(), user_id uuid not null, event_type text not null, target_id uuid, amount numeric(14,2) not null default 0, created_at timestamptz not null default now());
create table if not exists public.koja_payout_requests (id uuid primary key default gen_random_uuid(), user_id uuid not null, amount numeric(14,2) not null, currency text not null default 'ZMW', phone text not null, status text not null default 'pending', admin_note text default '', processed_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create index if not exists koja_payout_user_idx on public.koja_payout_requests(user_id,status,created_at desc);

create table if not exists public.koja_seller_verifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null unique, legal_name text not null,
 phone text default '', document_type text not null, document_number text not null,
 status text not null default 'pending', admin_note text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_seller_verifications_status_idx on public.koja_seller_verifications(status,created_at desc);

create table if not exists public.koja_referrals (
 id uuid primary key default gen_random_uuid(), referrer_id uuid not null, referred_user_id uuid,
 code text not null, reward_amount numeric(14,2) not null default 0, status text not null default 'active',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_referrals_referrer_idx on public.koja_referrals(referrer_id,created_at desc);
create index if not exists koja_referrals_code_idx on public.koja_referrals(code);

create table if not exists public.koja_ai_subscriptions (
 id uuid primary key default gen_random_uuid(), user_id uuid not null unique, plan text not null default 'free',
 monthly_price numeric(14,2) not null default 0, status text not null default 'active',
 started_at timestamptz default now(), expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.koja_ai_usage (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, usage_date date not null default current_date,
 requests integer not null default 0, input_tokens bigint not null default 0, output_tokens bigint not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(user_id,usage_date)
);
create index if not exists koja_ai_usage_user_date_idx on public.koja_ai_usage(user_id,usage_date desc);

create table if not exists public.koja_security_events (
 id uuid primary key default gen_random_uuid(), user_id uuid, event_type text not null, ip_address text default '',
 user_agent text default '', details jsonb default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists koja_security_events_date_idx on public.koja_security_events(created_at desc);

create table if not exists public.koja_seller_verifications (id uuid primary key default gen_random_uuid(), user_id uuid not null unique, legal_name text not null, phone text default '', document_type text not null, document_number text not null, status text not null default 'pending', admin_note text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create index if not exists koja_seller_verifications_status_idx on public.koja_seller_verifications(status,created_at desc);
create table if not exists public.koja_referrals (id uuid primary key default gen_random_uuid(), referrer_id uuid not null, referred_user_id uuid, code text not null, reward_amount numeric(14,2) not null default 0, status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create index if not exists koja_referrals_referrer_idx on public.koja_referrals(referrer_id,created_at desc);
create index if not exists koja_referrals_code_idx on public.koja_referrals(code);
create table if not exists public.koja_ai_subscriptions (id uuid primary key default gen_random_uuid(), user_id uuid not null unique, plan text not null default 'free', monthly_price numeric(14,2) not null default 0, status text not null default 'active', started_at timestamptz default now(), expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create table if not exists public.koja_ai_usage (id uuid primary key default gen_random_uuid(), user_id uuid not null, usage_date date not null default current_date, requests integer not null default 0, input_tokens bigint not null default 0, output_tokens bigint not null default 0, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(user_id,usage_date));
create index if not exists koja_ai_usage_user_date_idx on public.koja_ai_usage(user_id,usage_date desc);
create table if not exists public.koja_security_events (id uuid primary key default gen_random_uuid(), user_id uuid, event_type text not null, ip_address text default '', user_agent text default '', details jsonb default '{}'::jsonb, created_at timestamptz not null default now());
create index if not exists koja_security_events_date_idx on public.koja_security_events(created_at desc);
