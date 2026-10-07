-- KOJA BUSINESS HUB V5 — schema (run once in the Supabase SQL editor; safe to re-run)
-- Ids that point at existing tables are stored as text so this works whatever id
-- type your current koja_businesses / users tables use. The server uses the service key.

-- ============ Company profiles, services, pricing ============
create table if not exists koja_business_profiles (
  id             uuid primary key,
  business_id    text not null unique,
  slug           text not null unique,
  public_name    text not null,
  tagline        text default '',
  description    text default '',
  industry       text default '',      -- manufacturing|mining|agriculture|construction|energy|transport|technology|finance|healthcare|media
  location       text default '',
  country        text default '',
  website        text default '',
  contact_email  text default '',
  contact_phone  text default '',
  year_founded   int,
  employee_range text default '',
  certifications text default '',
  logo_url       text default '',
  show_catalogue boolean not null default false,
  accepts_rfq    boolean not null default true,
  status         text not null default 'draft',   -- draft | published | suspended
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index if not exists koja_business_profiles_status_idx on koja_business_profiles (status, industry);

create table if not exists koja_business_services (
  id            uuid primary key,
  business_id   text not null,
  name          text not null,
  description   text default '',
  pricing_model text not null default 'quote',     -- fixed | hourly | daily | quote
  price         numeric(14,2) not null default 0,
  currency      text not null default 'ZMW',
  active        boolean not null default true,
  created_at    timestamptz not null default now()
);
create index if not exists koja_business_services_biz_idx on koja_business_services (business_id);

create table if not exists koja_business_price_tiers (
  id          uuid primary key,
  business_id text not null,
  product_id  text not null,
  min_qty     int  not null check (min_qty >= 2),
  unit_price  numeric(14,2) not null check (unit_price > 0),
  label       text default '',
  created_at  timestamptz not null default now()
);
create index if not exists koja_business_price_tiers_biz_idx on koja_business_price_tiers (business_id, product_id);

-- ============ POS / inventory ============
create table if not exists koja_business_pos_receipts (
  id             uuid primary key,
  receipt_number text not null,
  business_id    text not null,
  sale_id        text,
  cashier_id     text,
  customer_name  text default '',
  payment_method text not null default 'cash',
  lines          jsonb not null default '[]'::jsonb,
  subtotal       numeric(14,2) not null default 0,
  discount       numeric(14,2) not null default 0,
  total          numeric(14,2) not null default 0,
  tendered       numeric(14,2) not null default 0,
  change_due     numeric(14,2) not null default 0,
  currency       text not null default 'ZMW',
  status         text not null default 'completed',  -- completed | void
  created_at     timestamptz not null default now(),
  unique (business_id, receipt_number)
);
create index if not exists koja_business_pos_receipts_biz_idx on koja_business_pos_receipts (business_id, created_at desc);

create table if not exists koja_business_stock_movements (
  id            uuid primary key default gen_random_uuid(),
  business_id   text,
  product_id    text,
  movement_type text,
  quantity      numeric,
  reference     text,
  created_at    timestamptz not null default now()
);

-- Optional columns on tables you already have (no-ops if the table is absent).
alter table if exists koja_business_sales add column if not exists payment_method text;
alter table if exists koja_business_sales add column if not exists receipt_number  text;
alter table if exists koja_business_sales add column if not exists source          text;
alter table if exists koja_business_sales add column if not exists customer_name   text;

create table if not exists koja_business_sale_items (
  id         uuid primary key default gen_random_uuid(),
  sale_id    text,
  product_id text,
  name       text,
  quantity   numeric,
  unit_price numeric(14,2),
  cost_price numeric(14,2),
  line_total numeric(14,2),
  created_at timestamptz not null default now()
);
alter table if exists koja_business_sale_items add column if not exists product_id text;
alter table if exists koja_business_sale_items add column if not exists name       text;
alter table if exists koja_business_sale_items add column if not exists unit_price numeric(14,2);
alter table if exists koja_business_sale_items add column if not exists cost_price numeric(14,2);
alter table if exists koja_business_sale_items add column if not exists line_total numeric(14,2);

-- ============ KOJA Connect+ ============
create table if not exists koja_connectplus_rfq_targets (
  id                 uuid primary key,
  request_id         text not null,
  target_business_id text not null,
  created_at         timestamptz not null default now()
);
create index if not exists koja_connectplus_rfq_targets_idx on koja_connectplus_rfq_targets (target_business_id);

create table if not exists koja_connectplus_contracts (
  id                  uuid primary key,
  contract_no         text not null unique,
  title               text not null,
  party_a_business_id text not null,
  party_b_business_id text not null,
  created_by          text,
  terms               text not null,
  terms_hash          text,                          -- SHA-256, fixed when the contract is sent
  value               numeric(16,2) default 0,
  currency            text default 'ZMW',
  start_date          date,
  end_date            date,
  reference           text default '',
  status              text not null default 'draft', -- draft|sent|active|rejected|withdrawn|completed|terminated
  sent_at             timestamptz,
  accepted_by         text,
  accepted_at         timestamptz,
  closed_reason       text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
create index if not exists koja_connectplus_contracts_a_idx on koja_connectplus_contracts (party_a_business_id);
create index if not exists koja_connectplus_contracts_b_idx on koja_connectplus_contracts (party_b_business_id);

create table if not exists koja_connectplus_partnerships (
  id                   uuid primary key,
  proposer_business_id text not null,
  partner_business_id  text not null,
  partnership_type     text not null default 'other',
  message              text default '',
  status               text not null default 'proposed',  -- proposed|accepted|declined|withdrawn|ended
  created_by           text,
  responded_at         timestamptz,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
create index if not exists koja_connectplus_partnerships_a_idx on koja_connectplus_partnerships (proposer_business_id);
create index if not exists koja_connectplus_partnerships_b_idx on koja_connectplus_partnerships (partner_business_id);

create table if not exists koja_connectplus_investor_profiles (
  id             uuid primary key,
  user_id        text not null unique,
  display_name   text not null,
  organisation   text default '',
  thesis         text default '',
  ticket_min     numeric(16,2) default 0,
  ticket_max     numeric(16,2) default 0,
  currency       text default 'USD',
  industries     jsonb not null default '[]'::jsonb,
  countries      text default '',
  contact_email  text,
  status         text not null default 'pending',   -- pending|approved|rejected|suspended
  declaration_at timestamptz,
  reviewed_by    text,
  reviewed_at    timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create table if not exists koja_connectplus_investment_listings (
  id            uuid primary key,
  business_id   text not null,
  title         text not null,
  summary       text not null,
  amount_sought numeric(16,2) not null,
  currency      text default 'USD',
  instrument    text default 'other',               -- equity|debt|revenue_share|convertible|other
  industry      text default '',
  use_of_funds  text default '',
  status        text not null default 'pending',    -- pending|published|rejected|closed
  review_note   text,
  created_by    text,
  reviewed_by   text,
  reviewed_at   timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists koja_connectplus_listings_idx on koja_connectplus_investment_listings (status, business_id);

create table if not exists koja_connectplus_investor_interests (
  id                  uuid primary key,
  listing_id          text not null,
  investor_user_id    text not null,
  investor_profile_id text,
  message             text default '',
  status              text not null default 'sent',  -- sent|accepted|declined
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (listing_id, investor_user_id)
);
