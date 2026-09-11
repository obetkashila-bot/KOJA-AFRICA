-- KOJA Market Live Shopping V1
-- Additive migration. Does not drop or truncate existing data.
create table if not exists public.koja_market_live_rooms (
  id text primary key,
  seller_id uuid not null,
  title text not null default 'Live Shopping',
  status text not null default 'live',
  pinned_product_id uuid,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_market_live_rooms_status_idx on public.koja_market_live_rooms(status, started_at desc);
create index if not exists koja_market_live_rooms_seller_idx on public.koja_market_live_rooms(seller_id, started_at desc);
alter table public.koja_market_live_rooms add column if not exists pinned_product_id uuid;
alter table public.koja_market_live_rooms add column if not exists ended_at timestamptz;
