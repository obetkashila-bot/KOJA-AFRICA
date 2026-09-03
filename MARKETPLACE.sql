-- KOJA AFRICA Digital Marketplace
-- Run once in Supabase SQL Editor.

create table if not exists public.koja_marketplace_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null,
 category text not null default 'Other',
 price numeric(12,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 cover_url text,
 file_url text,
 file_name text,
 file_size bigint,
 is_published boolean not null default false,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_marketplace_products_feed_idx on public.koja_marketplace_products(is_published, created_at desc);
create index if not exists koja_marketplace_products_seller_idx on public.koja_marketplace_products(seller_id, created_at desc);

create table if not exists public.koja_marketplace_orders (
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references public.koja_marketplace_products(id) on delete cascade,
 buyer_id uuid not null,
 seller_id uuid not null,
 amount numeric(12,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_marketplace_orders_buyer_idx on public.koja_marketplace_orders(buyer_id, created_at desc);
create index if not exists koja_marketplace_orders_seller_idx on public.koja_marketplace_orders(seller_id, created_at desc);
create unique index if not exists koja_marketplace_free_order_unique on public.koja_marketplace_orders(product_id, buyer_id) where amount = 0;
