-- KOJA V8 Market Delivery V2 -- production hardening
-- Safe/idempotent. Does not modify Communications/WebRTC/FCM/LiveKit.

alter table public.koja_market_delivery_jobs add column if not exists route_distance_km numeric(12,3);
alter table public.koja_market_delivery_jobs add column if not exists route_duration_minutes integer;
alter table public.koja_market_delivery_jobs add column if not exists route_geometry jsonb;
alter table public.koja_market_delivery_jobs add column if not exists rejected_driver_id uuid;
alter table public.koja_market_delivery_jobs add column if not exists rejection_count integer not null default 0;
alter table public.koja_market_delivery_jobs add column if not exists last_status_at timestamptz default now();

create table if not exists public.koja_market_delivery_earnings (
 id uuid primary key default gen_random_uuid(),
 delivery_job_id uuid not null unique references public.koja_market_delivery_jobs(id) on delete cascade,
 order_id uuid,
 driver_id uuid not null,
 gross_fee numeric(14,2) not null default 0,
 driver_amount numeric(14,2) not null default 0,
 koja_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'earned',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_delivery_earnings_driver_idx on public.koja_market_delivery_earnings(driver_id,status,created_at desc);

create index if not exists koja_market_delivery_jobs_status_idx on public.koja_market_delivery_jobs(status,created_at desc);
create index if not exists koja_market_delivery_jobs_coords_idx on public.koja_market_delivery_jobs(pickup_latitude,pickup_longitude,status);

-- Prevent duplicate earnings for the same completed delivery.
create unique index if not exists koja_market_delivery_earnings_job_uidx on public.koja_market_delivery_earnings(delivery_job_id);
