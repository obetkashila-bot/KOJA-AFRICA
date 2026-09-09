create table if not exists public.koja_ai_conversations (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 title text not null default 'New KOJA AI chat', is_archived boolean not null default false,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_ai_conversations_user_idx on public.koja_ai_conversations(user_id, updated_at desc);
create table if not exists public.koja_ai_messages (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_ai_conversations(id) on delete cascade,
 user_id uuid not null, role text not null check (role in ('user','assistant')), content text not null,
 created_at timestamptz not null default now()
);
create index if not exists koja_ai_messages_conversation_idx on public.koja_ai_messages(conversation_id, created_at asc);
create index if not exists koja_ai_messages_user_idx on public.koja_ai_messages(user_id, created_at desc);
notify pgrst, 'reload schema';

create table if not exists public.koja_news_reactions (post_id uuid not null references public.koja_public_posts(id) on delete cascade,user_id uuid not null,reaction text not null default 'like',created_at timestamptz default now(),primary key(post_id,user_id));
create index if not exists koja_news_reactions_post_idx on public.koja_news_reactions(post_id);
create table if not exists public.koja_media_events (id uuid primary key default gen_random_uuid(),post_id uuid references public.koja_public_posts(id) on delete cascade,user_id uuid,session_id text not null,event_type text not null,watch_seconds numeric default 0,completion_percent numeric default 0,created_at timestamptz default now());
create index if not exists koja_media_events_post_idx on public.koja_media_events(post_id,created_at desc);
create index if not exists koja_media_events_session_idx on public.koja_media_events(session_id,created_at desc);
create table if not exists public.koja_ai_feedback (id uuid primary key default gen_random_uuid(),user_id uuid,rating text,prompt_hash text,created_at timestamptz default now());

create table if not exists public.koja_market_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null default '',
 category text not null default 'Other',
 product_type text not null default 'physical',
 price numeric(14,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 stock integer not null default 1 check (stock >= 0),
 sku text,
 image_url text,
 digital_file_url text,
 digital_file_name text,
 delivery_available boolean not null default true,
 delivery_fee numeric(14,2) not null default 0 check (delivery_fee >= 0),
 location text,
 is_published boolean not null default false,
 approval_status text not null default 'pending',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_products_feed_idx on public.koja_market_products(is_published,approval_status,created_at desc);
create index if not exists koja_market_products_seller_idx on public.koja_market_products(seller_id,created_at desc);
create index if not exists koja_market_products_category_idx on public.koja_market_products(category,created_at desc);

create table if not exists public.koja_market_orders (
 id uuid primary key default gen_random_uuid(),
 order_number text unique not null,
 product_id uuid not null references public.koja_market_products(id) on delete restrict,
 buyer_id uuid not null,
 seller_id uuid not null,
 quantity integer not null default 1 check (quantity > 0),
 item_amount numeric(14,2) not null default 0,
 delivery_fee numeric(14,2) not null default 0,
 total_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0,
 seller_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 payment_transaction_id text,
 recipient_name text,
 recipient_phone text,
 delivery_address text,
 notes text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_orders_buyer_idx on public.koja_market_orders(buyer_id,created_at desc);
create index if not exists koja_market_orders_seller_idx on public.koja_market_orders(seller_id,created_at desc);
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);

create table if not exists public.koja_market_sellers (
 id uuid primary key default gen_random_uuid(),
 user_id uuid unique not null,
 store_name text not null,
 description text default '',
 phone text,
 location text,
 approval_status text not null default 'pending',
 is_active boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_sellers_status_idx on public.koja_market_sellers(approval_status,is_active);

-- Safe compatibility additions when the tables already exist.
alter table public.koja_market_products add column if not exists product_type text default 'physical';
alter table public.koja_market_products add column if not exists stock integer default 1;
alter table public.koja_market_products add column if not exists sku text;
alter table public.koja_market_products add column if not exists image_url text;
alter table public.koja_market_products add column if not exists digital_file_url text;
alter table public.koja_market_products add column if not exists digital_file_name text;
alter table public.koja_market_products add column if not exists delivery_available boolean default true;
alter table public.koja_market_products add column if not exists delivery_fee numeric(14,2) default 0;
alter table public.koja_market_products add column if not exists location text;
alter table public.koja_market_products add column if not exists approval_status text default 'pending';

create table if not exists public.koja_market_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null default '',
 category text not null default 'Other',
 product_type text not null default 'physical',
 price numeric(14,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 stock integer not null default 1 check (stock >= 0),
 sku text,
 image_url text,
 digital_file_url text,
 digital_file_name text,
 delivery_available boolean not null default true,
 delivery_fee numeric(14,2) not null default 0 check (delivery_fee >= 0),
 location text,
 is_published boolean not null default false,
 approval_status text not null default 'pending',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_products_feed_idx on public.koja_market_products(is_published,approval_status,created_at desc);
create index if not exists koja_market_products_seller_idx on public.koja_market_products(seller_id,created_at desc);
create index if not exists koja_market_products_category_idx on public.koja_market_products(category,created_at desc);

create table if not exists public.koja_market_orders (
 id uuid primary key default gen_random_uuid(),
 order_number text unique not null,
 product_id uuid not null references public.koja_market_products(id) on delete restrict,
 buyer_id uuid not null,
 seller_id uuid not null,
 quantity integer not null default 1 check (quantity > 0),
 item_amount numeric(14,2) not null default 0,
 delivery_fee numeric(14,2) not null default 0,
 total_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0,
 seller_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 payment_transaction_id text,
 recipient_name text,
 recipient_phone text,
 delivery_address text,
 notes text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_orders_buyer_idx on public.koja_market_orders(buyer_id,created_at desc);
create index if not exists koja_market_orders_seller_idx on public.koja_market_orders(seller_id,created_at desc);
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);

create table if not exists public.koja_market_sellers (
 id uuid primary key default gen_random_uuid(),
 user_id uuid unique not null,
 store_name text not null,
 description text default '',
 phone text,
 location text,
 approval_status text not null default 'pending',
 is_active boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_sellers_status_idx on public.koja_market_sellers(approval_status,is_active);

-- Safe compatibility additions when the tables already exist.
alter table public.koja_market_products add column if not exists product_type text default 'physical';
alter table public.koja_market_products add column if not exists stock integer default 1;
alter table public.koja_market_products add column if not exists sku text;
alter table public.koja_market_products add column if not exists image_url text;
alter table public.koja_market_products add column if not exists digital_file_url text;
alter table public.koja_market_products add column if not exists digital_file_name text;
alter table public.koja_market_products add column if not exists delivery_available boolean default true;
alter table public.koja_market_products add column if not exists delivery_fee numeric(14,2) default 0;
alter table public.koja_market_products add column if not exists location text;
alter table public.koja_market_products add column if not exists approval_status text default 'pending';
create table if not exists public.koja_market_cart (id uuid primary key default gen_random_uuid(), user_id uuid not null, product_id uuid not null references public.koja_market_products(id) on delete cascade, quantity integer not null default 1 check(quantity>0), created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(user_id,product_id));
create table if not exists public.koja_market_wishlist (id uuid primary key default gen_random_uuid(), user_id uuid not null, product_id uuid not null references public.koja_market_products(id) on delete cascade, created_at timestamptz not null default now(), unique(user_id,product_id));
-- KOJA MARKET V3 + KOJA BUSINESS commercial engine
-- Run after KOJA_MARKET.sql / KOJA_MARKET_V2.sql. All statements are idempotent.

alter table public.koja_market_orders add column if not exists platform_fee numeric(14,2) not null default 0;
alter table public.koja_market_orders add column if not exists payout_status text not null default 'pending';
alter table public.koja_market_orders add column if not exists delivery_status text not null default 'not_requested';

create table if not exists public.koja_market_seller_subscriptions (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null references public.koja_market_sellers(id) on delete cascade,
 user_id uuid not null, plan text not null default 'free', monthly_price numeric(14,2) not null default 0,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(seller_id)
);
create index if not exists koja_market_seller_subs_user_idx on public.koja_market_seller_subscriptions(user_id,status);

create table if not exists public.koja_market_featured (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 seller_id uuid not null, days integer not null default 7, price numeric(14,2) not null default 0,
 status text not null default 'pending', starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now()
);
create index if not exists koja_market_featured_active_idx on public.koja_market_featured(status,ends_at);

create table if not exists public.koja_market_ads (
 id uuid primary key default gen_random_uuid(), advertiser_id uuid not null, title text not null,
 target_url text, placement text not null default 'market', budget numeric(14,2) not null default 0,
 spent numeric(14,2) not null default 0, status text not null default 'pending', impressions bigint not null default 0,
 clicks bigint not null default 0, starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_ads_status_idx on public.koja_market_ads(status,placement);

create table if not exists public.koja_market_reviews (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 buyer_id uuid not null, rating integer not null check(rating between 1 and 5), review text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(product_id,buyer_id)
);

create table if not exists public.koja_market_ledger (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 seller_id uuid not null, buyer_id uuid, gross_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0, platform_fee numeric(14,2) not null default 0,
 net_amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 status text not null default 'pending', created_at timestamptz not null default now()
);
create index if not exists koja_market_ledger_seller_idx on public.koja_market_ledger(seller_id,created_at desc);

create table if not exists public.koja_market_payment_fees (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 buyer_id uuid, amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 fee_type text not null default 'platform_service_fee', provider text, reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_market_delivery_jobs (
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.koja_market_orders(id) on delete cascade,
 customer_id uuid, driver_id uuid, pickup_address text, delivery_address text, delivery_fee numeric(14,2) not null default 0,
 status text not null default 'requested', tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_delivery_jobs_status_idx on public.koja_market_delivery_jobs(status,created_at desc);

-- Business SaaS
create table if not exists public.koja_businesses (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null,
 category text not null default 'General', phone text, location text, logo_url text,
 currency text not null default 'ZMW', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_businesses_owner_idx on public.koja_businesses(owner_id,created_at desc);

create table if not exists public.koja_business_subscriptions (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 owner_id uuid not null, plan text not null default 'starter', monthly_price numeric(14,2) not null default 99,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_products (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, sku text, selling_price numeric(14,2) not null default 0, cost_price numeric(14,2) not null default 0,
 stock integer not null default 0, reorder_level integer not null default 0, active boolean not null default true,
 market_product_id uuid references public.koja_market_products(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_products_biz_idx on public.koja_business_products(business_id,created_at desc);

create table if not exists public.koja_business_stock_movements (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 product_id uuid not null references public.koja_business_products(id) on delete cascade, movement_type text not null,
 quantity integer not null, reference text, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_sales (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 customer_id uuid, product_id uuid, invoice_id uuid, quantity integer not null default 1,
 total_amount numeric(14,2) not null default 0, payment_method text, status text not null default 'paid', description text default '', created_at timestamptz not null default now()
);
create index if not exists koja_business_sales_biz_idx on public.koja_business_sales(business_id,created_at desc);

create table if not exists public.koja_business_expenses (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 supplier_id uuid, category text, amount numeric(14,2) not null default 0, description text default '', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_customers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_customers_biz_idx on public.koja_business_customers(business_id,name);

create table if not exists public.koja_business_suppliers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_invoices (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 invoice_number text not null, customer_id uuid, subtotal numeric(14,2) not null default 0,
 tax_amount numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0,
 status text not null default 'draft', due_date date, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id,invoice_number)
);

create table if not exists public.koja_business_invoice_items (
 id uuid primary key default gen_random_uuid(), invoice_id uuid not null references public.koja_business_invoices(id) on delete cascade,
 product_id uuid, description text not null, quantity numeric(14,2) not null default 1, unit_price numeric(14,2) not null default 0, total numeric(14,2) not null default 0
);

create table if not exists public.koja_business_employees (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, role text, salary numeric(14,2) not null default 0,
 pay_frequency text not null default 'monthly', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_payroll (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 employee_id uuid not null references public.koja_business_employees(id) on delete cascade, period_start date not null,
 period_end date not null, gross_pay numeric(14,2) not null default 0, deductions numeric(14,2) not null default 0,
 net_pay numeric(14,2) not null default 0, status text not null default 'pending', paid_at timestamptz, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_stores (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 slug text unique not null, store_name text not null, description text default '', published boolean not null default false,
 market_enabled boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_ai_usage (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 user_id uuid, prompt text, response_summary text, tokens integer not null default 0, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_payments (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 amount numeric(14,2) not null default 0, currency text not null default 'ZMW', method text, provider text,
 reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_delivery (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 order_reference text, customer_id uuid, address text, fee numeric(14,2) not null default 0,
 status text not null default 'requested', driver_id uuid, tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_ai_plans (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 plan text not null default 'included', monthly_limit integer not null default 100, used_count integer not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);
-- KOJA MARKET V3 + KOJA BUSINESS commercial engine
-- Run after KOJA_MARKET.sql / KOJA_MARKET_V2.sql. All statements are idempotent.

alter table public.koja_market_orders add column if not exists platform_fee numeric(14,2) not null default 0;
alter table public.koja_market_orders add column if not exists payout_status text not null default 'pending';
alter table public.koja_market_orders add column if not exists delivery_status text not null default 'not_requested';

create table if not exists public.koja_market_seller_subscriptions (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null references public.koja_market_sellers(id) on delete cascade,
 user_id uuid not null, plan text not null default 'free', monthly_price numeric(14,2) not null default 0,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(seller_id)
);
create index if not exists koja_market_seller_subs_user_idx on public.koja_market_seller_subscriptions(user_id,status);

create table if not exists public.koja_market_featured (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 seller_id uuid not null, days integer not null default 7, price numeric(14,2) not null default 0,
 status text not null default 'pending', starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now()
);
create index if not exists koja_market_featured_active_idx on public.koja_market_featured(status,ends_at);

create table if not exists public.koja_market_ads (
 id uuid primary key default gen_random_uuid(), advertiser_id uuid not null, title text not null,
 target_url text, placement text not null default 'market', budget numeric(14,2) not null default 0,
 spent numeric(14,2) not null default 0, status text not null default 'pending', impressions bigint not null default 0,
 clicks bigint not null default 0, starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_ads_status_idx on public.koja_market_ads(status,placement);

create table if not exists public.koja_market_reviews (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 buyer_id uuid not null, rating integer not null check(rating between 1 and 5), review text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(product_id,buyer_id)
);

create table if not exists public.koja_market_ledger (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 seller_id uuid not null, buyer_id uuid, gross_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0, platform_fee numeric(14,2) not null default 0,
 net_amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 status text not null default 'pending', created_at timestamptz not null default now()
);
create index if not exists koja_market_ledger_seller_idx on public.koja_market_ledger(seller_id,created_at desc);

create table if not exists public.koja_market_payment_fees (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 buyer_id uuid, amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 fee_type text not null default 'platform_service_fee', provider text, reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_market_delivery_jobs (
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.koja_market_orders(id) on delete cascade,
 customer_id uuid, driver_id uuid, pickup_address text, delivery_address text, delivery_fee numeric(14,2) not null default 0,
 status text not null default 'requested', tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_delivery_jobs_status_idx on public.koja_market_delivery_jobs(status,created_at desc);

-- Business SaaS
create table if not exists public.koja_businesses (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null,
 category text not null default 'General', phone text, location text, logo_url text,
 currency text not null default 'ZMW', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_businesses_owner_idx on public.koja_businesses(owner_id,created_at desc);

create table if not exists public.koja_business_subscriptions (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 owner_id uuid not null, plan text not null default 'starter', monthly_price numeric(14,2) not null default 99,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_products (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, sku text, selling_price numeric(14,2) not null default 0, cost_price numeric(14,2) not null default 0,
 stock integer not null default 0, reorder_level integer not null default 0, active boolean not null default true,
 market_product_id uuid references public.koja_market_products(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_products_biz_idx on public.koja_business_products(business_id,created_at desc);

create table if not exists public.koja_business_stock_movements (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 product_id uuid not null references public.koja_business_products(id) on delete cascade, movement_type text not null,
 quantity integer not null, reference text, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_sales (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 customer_id uuid, product_id uuid, invoice_id uuid, quantity integer not null default 1,
 total_amount numeric(14,2) not null default 0, payment_method text, status text not null default 'paid', description text default '', created_at timestamptz not null default now()
);
create index if not exists koja_business_sales_biz_idx on public.koja_business_sales(business_id,created_at desc);

create table if not exists public.koja_business_expenses (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 supplier_id uuid, category text, amount numeric(14,2) not null default 0, description text default '', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_customers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_customers_biz_idx on public.koja_business_customers(business_id,name);

create table if not exists public.koja_business_suppliers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_invoices (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 invoice_number text not null, customer_id uuid, subtotal numeric(14,2) not null default 0,
 tax_amount numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0,
 status text not null default 'draft', due_date date, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id,invoice_number)
);

create table if not exists public.koja_business_invoice_items (
 id uuid primary key default gen_random_uuid(), invoice_id uuid not null references public.koja_business_invoices(id) on delete cascade,
 product_id uuid, description text not null, quantity numeric(14,2) not null default 1, unit_price numeric(14,2) not null default 0, total numeric(14,2) not null default 0
);

create table if not exists public.koja_business_employees (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, role text, salary numeric(14,2) not null default 0,
 pay_frequency text not null default 'monthly', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_payroll (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 employee_id uuid not null references public.koja_business_employees(id) on delete cascade, period_start date not null,
 period_end date not null, gross_pay numeric(14,2) not null default 0, deductions numeric(14,2) not null default 0,
 net_pay numeric(14,2) not null default 0, status text not null default 'pending', paid_at timestamptz, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_stores (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 slug text unique not null, store_name text not null, description text default '', published boolean not null default false,
 market_enabled boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_ai_usage (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 user_id uuid, prompt text, response_summary text, tokens integer not null default 0, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_payments (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 amount numeric(14,2) not null default 0, currency text not null default 'ZMW', method text, provider text,
 reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_delivery (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 order_reference text, customer_id uuid, address text, fee numeric(14,2) not null default 0,
 status text not null default 'requested', driver_id uuid, tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_ai_plans (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 plan text not null default 'included', monthly_limit integer not null default 100, used_count integer not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);


-- V4 production commerce additions
create table if not exists public.koja_market_payouts (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null, user_id uuid not null,
 amount numeric(14,2) not null check(amount>0), currency text not null default 'ZMW', method text not null default 'mobile_money',
 destination text not null, status text not null default 'requested', provider_reference text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_payouts_seller_idx on public.koja_market_payouts(seller_id,status,created_at desc);

create table if not exists public.koja_market_coupons (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null, code text not null,
 discount_percent numeric(6,2) not null check(discount_percent>0 and discount_percent<=100),
 usage_limit integer not null default 0, used_count integer not null default 0, active boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(seller_id,code)
);
create index if not exists koja_market_coupons_code_idx on public.koja_market_coupons(code,active);

alter table public.koja_business_products add column if not exists low_stock_alert boolean not null default true;
alter table public.koja_business_products add column if not exists barcode text;
alter table public.koja_business_subscriptions add column if not exists provider text;
alter table public.koja_business_subscriptions add column if not exists payment_reference text;
alter table public.koja_market_ads add column if not exists billing_status text not null default 'unbilled';
alter table public.koja_market_featured add column if not exists billing_status text not null default 'unbilled';

-- Optional reconciliation/reporting indexes
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);
create index if not exists koja_market_payment_fees_status_idx on public.koja_market_payment_fees(status,created_at desc);
create index if not exists koja_business_payments_status_idx on public.koja_business_payments(status,created_at desc);
create index if not exists koja_business_delivery_status_idx on public.koja_business_delivery(status,created_at desc);

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


-- ============================================================
-- KOJA AFRICA V8 BUSINESS / POS MODULE
-- Idempotent migration
-- ============================================================
create table if not exists public.koja_businesses (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null, category text not null default 'General', phone text, location text, logo_url text, currency text not null default 'ZMW', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_businesses_owner_idx on public.koja_businesses(owner_id,created_at desc);
create table if not exists public.koja_business_subscriptions (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, owner_id uuid not null, plan text not null default 'starter', monthly_price numeric(14,2) not null default 99, status text not null default 'pending', started_at timestamptz, expires_at timestamptz, provider text, payment_reference text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);
create table if not exists public.koja_business_products (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, name text not null, sku text, selling_price numeric(14,2) not null default 0, cost_price numeric(14,2) not null default 0, stock integer not null default 0, reorder_level integer not null default 0, active boolean not null default true, market_product_id uuid, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_products_biz_idx on public.koja_business_products(business_id,created_at desc);
create table if not exists public.koja_business_stock_movements (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, product_id uuid not null references public.koja_business_products(id) on delete cascade, movement_type text not null, quantity integer not null, reference text, created_at timestamptz not null default now()
);
create table if not exists public.koja_business_sales (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, customer_id uuid, product_id uuid, invoice_id uuid, quantity integer not null default 1, total_amount numeric(14,2) not null default 0, payment_method text, status text not null default 'paid', description text default '', created_at timestamptz not null default now()
);
create index if not exists koja_business_sales_biz_idx on public.koja_business_sales(business_id,created_at desc);
create table if not exists public.koja_business_expenses (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, supplier_id uuid, category text, amount numeric(14,2) not null default 0, description text default '', created_at timestamptz not null default now()
);
create table if not exists public.koja_business_customers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.koja_business_suppliers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.koja_business_invoices (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, invoice_number text not null, customer_id uuid, subtotal numeric(14,2) not null default 0, tax_amount numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0, status text not null default 'draft', due_date date, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id,invoice_number)
);
create table if not exists public.koja_business_invoice_items (
 id uuid primary key default gen_random_uuid(), invoice_id uuid not null references public.koja_business_invoices(id) on delete cascade, product_id uuid, description text not null, quantity numeric(14,2) not null default 1, unit_price numeric(14,2) not null default 0, total numeric(14,2) not null default 0
);
create table if not exists public.koja_business_employees (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, name text not null, phone text, email text, role text, salary numeric(14,2) not null default 0, pay_frequency text not null default 'monthly', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.koja_business_payroll (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, employee_id uuid not null references public.koja_business_employees(id) on delete cascade, period_start date not null, period_end date not null, gross_pay numeric(14,2) not null default 0, deductions numeric(14,2) not null default 0, net_pay numeric(14,2) not null default 0, status text not null default 'pending', paid_at timestamptz, created_at timestamptz not null default now()
);
create table if not exists public.koja_business_stores (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, slug text unique not null, store_name text not null, description text default '', published boolean not null default false, market_enabled boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);
create table if not exists public.koja_business_ai_usage (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, user_id uuid, prompt text, response_summary text, tokens integer not null default 0, created_at timestamptz not null default now()
);
create table if not exists public.koja_business_payments (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, amount numeric(14,2) not null default 0, currency text not null default 'ZMW', method text, provider text, reference text, status text not null default 'pending', created_at timestamptz not null default now()
);
create table if not exists public.koja_business_delivery (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, order_reference text, customer_id uuid, address text, fee numeric(14,2) not null default 0, status text not null default 'requested', driver_id uuid, tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.koja_business_ai_plans (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade, plan text not null default 'included', monthly_limit integer not null default 100, used_count integer not null default 0, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);
alter table public.koja_business_subscriptions add column if not exists provider text;
alter table public.koja_business_subscriptions add column if not exists payment_reference text;
alter table public.koja_business_products add column if not exists low_stock_alert boolean not null default true;
alter table public.koja_business_products add column if not exists barcode text;
