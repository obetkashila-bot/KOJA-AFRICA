-- KOJA GLOBAL REVENUE + PAYMENTS V2
-- Additive/update-safe migration. Does not drop or recreate existing tables.

create table if not exists public.koja_revenue_v2_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  organization_id uuid null,
  external_reference text,
  provider text not null default 'manual',
  provider_transaction_id text,
  payment_method text,
  transaction_type text not null default 'sale',
  amount numeric(20,2) not null default 0,
  currency text not null default 'ZMW',
  fee_amount numeric(20,2) not null default 0,
  status text not null default 'pending',
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.koja_revenue_v2_commissions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  organization_id uuid null,
  transaction_id uuid null references public.koja_revenue_v2_transactions(id) on delete set null,
  recipient_id uuid null,
  commission_type text not null default 'platform',
  rate numeric(12,6) not null default 0,
  amount numeric(20,2) not null default 0,
  currency text not null default 'ZMW',
  status text not null default 'pending',
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.koja_revenue_v2_settlements (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  organization_id uuid null,
  provider text not null default 'flutterwave',
  reference text,
  amount numeric(20,2) not null default 0,
  currency text not null default 'ZMW',
  status text not null default 'pending',
  settlement_date date,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.koja_revenue_v2_payouts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  organization_id uuid null,
  recipient_id uuid null,
  provider text not null default 'flutterwave',
  destination text,
  reference text,
  amount numeric(20,2) not null default 0,
  currency text not null default 'ZMW',
  status text not null default 'pending',
  provider_payout_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.koja_revenue_v2_invoices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  organization_id uuid null,
  invoice_number text not null,
  customer_name text,
  customer_email text,
  amount numeric(20,2) not null default 0,
  currency text not null default 'ZMW',
  status text not null default 'issued',
  due_date date,
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, invoice_number)
);

create table if not exists public.koja_revenue_v2_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  organization_id uuid null,
  event_type text not null,
  entity_type text,
  entity_id uuid,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_krv2_tx_user_created on public.koja_revenue_v2_transactions(user_id, created_at desc);
create index if not exists idx_krv2_tx_org_created on public.koja_revenue_v2_transactions(organization_id, created_at desc);
create index if not exists idx_krv2_tx_provider_ref on public.koja_revenue_v2_transactions(provider, external_reference);
create index if not exists idx_krv2_tx_provider_id on public.koja_revenue_v2_transactions(provider, provider_transaction_id);
create index if not exists idx_krv2_comm_user_created on public.koja_revenue_v2_commissions(user_id, created_at desc);
create index if not exists idx_krv2_settle_user_created on public.koja_revenue_v2_settlements(user_id, created_at desc);
create index if not exists idx_krv2_payout_user_created on public.koja_revenue_v2_payouts(user_id, created_at desc);
create index if not exists idx_krv2_invoice_user_created on public.koja_revenue_v2_invoices(user_id, created_at desc);
create index if not exists idx_krv2_events_org_created on public.koja_revenue_v2_events(organization_id, created_at desc);

alter table public.koja_revenue_v2_transactions enable row level security;
alter table public.koja_revenue_v2_commissions enable row level security;
alter table public.koja_revenue_v2_settlements enable row level security;
alter table public.koja_revenue_v2_payouts enable row level security;
alter table public.koja_revenue_v2_invoices enable row level security;
alter table public.koja_revenue_v2_events enable row level security;

do $$ begin
  create policy krv2_tx_owner on public.koja_revenue_v2_transactions for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy krv2_comm_owner on public.koja_revenue_v2_commissions for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy krv2_settle_owner on public.koja_revenue_v2_settlements for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy krv2_payout_owner on public.koja_revenue_v2_payouts for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy krv2_invoice_owner on public.koja_revenue_v2_invoices for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy krv2_event_owner on public.koja_revenue_v2_events for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
exception when duplicate_object then null; end $$;

comment on table public.koja_revenue_v2_transactions is 'KOJA unified revenue/payment operating ledger; not a replacement for statutory accounting.';
comment on table public.koja_revenue_v2_payouts is 'KOJA payout instructions/records; actual provider transfer must be explicitly executed and verified.';
