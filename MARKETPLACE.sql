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
 payment_transaction_id text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_marketplace_orders_buyer_idx on public.koja_marketplace_orders(buyer_id, created_at desc);
create index if not exists koja_marketplace_orders_seller_idx on public.koja_marketplace_orders(seller_id, created_at desc);
create unique index if not exists koja_marketplace_free_order_unique on public.koja_marketplace_orders(product_id, buyer_id) where amount = 0;

-- Marketplace social posts: sellers/users can publish product-related image/video posts.
create table if not exists public.koja_marketplace_posts (
 id uuid primary key default gen_random_uuid(),
 author_id uuid not null,
 product_id uuid references public.koja_marketplace_products(id) on delete set null,
 title text,
 body text not null,
 media_url text,
 media_type text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 is_published boolean not null default true
);
create index if not exists koja_marketplace_posts_feed_idx on public.koja_marketplace_posts(is_published, created_at desc);
create index if not exists koja_marketplace_posts_author_idx on public.koja_marketplace_posts(author_id, created_at desc);
create index if not exists koja_marketplace_posts_product_idx on public.koja_marketplace_posts(product_id, created_at desc);

-- Seller commission and payout system.
-- Default KOJA commission is 10%; configure MARKETPLACE_COMMISSION_PERCENT in Render.
alter table public.koja_marketplace_orders
  add column if not exists commission_amount numeric(12,2) not null default 0,
  add column if not exists seller_net_amount numeric(12,2) not null default 0;

create table if not exists public.koja_marketplace_payouts (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 amount numeric(12,2) not null check (amount > 0),
 currency text not null default 'ZMW',
 status text not null default 'pending',
 method text not null,
 account_number text not null,
 account_name text not null,
 admin_note text,
 processed_at timestamptz,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_marketplace_payouts_seller_idx on public.koja_marketplace_payouts(seller_id, created_at desc);
create index if not exists koja_marketplace_payouts_status_idx on public.koja_marketplace_payouts(status, created_at desc);
