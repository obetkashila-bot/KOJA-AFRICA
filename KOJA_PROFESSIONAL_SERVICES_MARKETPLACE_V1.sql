create extension if not exists pgcrypto;
create table if not exists public.koja_professional_services (
 id uuid primary key default gen_random_uuid(), provider_id uuid not null, title text not null,
 description text, category text, service_type text not null default 'project', price numeric(14,2) default 0,
 currency text default 'ZMW', duration_minutes integer, online_available boolean default true,
 in_person_available boolean default false, location text, status text default 'pending',
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_ps_services_provider_idx on public.koja_professional_services(provider_id,status);
create table if not exists public.koja_professional_requests (
 id uuid primary key default gen_random_uuid(), customer_id uuid not null, provider_id uuid, service_id uuid,
 title text not null, description text not null, category text, request_type text default 'project',
 budget numeric(14,2), currency text default 'ZMW', location text, deadline date, status text default 'open',
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_ps_requests_customer_idx on public.koja_professional_requests(customer_id,status,created_at desc);
create index if not exists koja_ps_requests_provider_idx on public.koja_professional_requests(provider_id,status,created_at desc);
create table if not exists public.koja_professional_quotes (
 id uuid primary key default gen_random_uuid(), request_id uuid not null, provider_id uuid not null,
 customer_id uuid not null, amount numeric(14,2) not null, currency text default 'ZMW', delivery_days integer,
 message text, status text default 'submitted', created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_ps_quotes_request_idx on public.koja_professional_quotes(request_id,status);
create table if not exists public.koja_professional_jobs (
 id uuid primary key default gen_random_uuid(), request_id uuid, quote_id uuid, service_id uuid,
 customer_id uuid not null, provider_id uuid not null, title text not null, amount numeric(14,2) default 0,
 currency text default 'ZMW', status text default 'awaiting_payment', payment_status text default 'pending',
 due_date date, submitted_at timestamptz, completed_at timestamptz, created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_ps_jobs_customer_idx on public.koja_professional_jobs(customer_id,status,created_at desc);
create index if not exists koja_ps_jobs_provider_idx on public.koja_professional_jobs(provider_id,status,created_at desc);
create table if not exists public.koja_professional_live_sessions (
 id uuid primary key default gen_random_uuid(), provider_id uuid not null, title text not null, description text,
 scheduled_at timestamptz, duration_minutes integer default 60, capacity integer default 1,
 price numeric(14,2) default 0, currency text default 'ZMW', mode text default 'online', status text default 'scheduled', created_at timestamptz default now()
);
create table if not exists public.koja_professional_live_attendees (
 id uuid primary key default gen_random_uuid(), session_id uuid not null, customer_id uuid not null,
 payment_status text default 'pending', attendance_status text default 'registered', created_at timestamptz default now(), unique(session_id,customer_id)
);
create table if not exists public.koja_professional_transactions (
 id uuid primary key default gen_random_uuid(), customer_id uuid, provider_id uuid, job_id uuid, session_id uuid,
 transaction_type text not null default 'service', external_reference text, provider_transaction_id text,
 gross_amount numeric(14,2) not null, commission_rate numeric(8,4) default 0, commission_amount numeric(14,2) default 0,
 processing_fee numeric(14,2) default 0, professional_amount numeric(14,2) default 0, currency text default 'ZMW',
 status text default 'pending', payout_status text default 'pending', metadata jsonb default '{}'::jsonb,
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_ps_tx_provider_idx on public.koja_professional_transactions(provider_id,status,created_at desc);
create table if not exists public.koja_professional_reviews (
 id uuid primary key default gen_random_uuid(), customer_id uuid not null, provider_id uuid not null, job_id uuid,
 rating integer not null check (rating between 1 and 5), review text, created_at timestamptz default now()
);
create index if not exists koja_ps_reviews_provider_idx on public.koja_professional_reviews(provider_id,created_at desc);
create table if not exists public.koja_professional_verifications (
 id uuid primary key default gen_random_uuid(), provider_id uuid not null, verification_type text not null,
 status text default 'pending', document_url text, admin_note text, verified_at timestamptz, created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists koja_ps_verify_provider_idx on public.koja_professional_verifications(provider_id,status);
create table if not exists public.koja_professional_commission_settings (
 id uuid primary key default gen_random_uuid(), service_type text not null unique, commission_rate numeric(8,4) not null default 10,
 currency text default 'ZMW', is_active boolean default true, updated_at timestamptz default now()
);
insert into public.koja_professional_commission_settings(service_type,commission_rate)
values ('appointment',10),('live',10),('project',10),('digital',10)
on conflict(service_type) do nothing;
