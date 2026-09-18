-- KOJA E2E V4 migration — additive/update-safe only.
create table if not exists public.koja_e2e_idempotency_keys (
  id uuid primary key default gen_random_uuid(),
  idempotency_key text not null unique,
  action text not null,
  status text not null default 'started',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_e2e_idempotency_action_idx on public.koja_e2e_idempotency_keys(action,created_at desc);

create table if not exists public.koja_e2e_ledger_entries (
  id uuid primary key default gen_random_uuid(),
  order_id uuid,
  source_type text,
  source_id text,
  entry_type text not null,
  direction text not null,
  amount numeric(14,2) not null default 0,
  currency text not null default 'ZMW',
  description text,
  reference text,
  idempotency_key text unique,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists koja_e2e_ledger_order_idx on public.koja_e2e_ledger_entries(order_id,created_at desc);
create index if not exists koja_e2e_ledger_source_idx on public.koja_e2e_ledger_entries(source_type,source_id,created_at desc);
create index if not exists koja_e2e_ledger_type_idx on public.koja_e2e_ledger_entries(entry_type,created_at desc);

create table if not exists public.koja_e2e_webhook_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  event_key text not null unique,
  event_type text,
  transaction_reference text,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'received',
  created_at timestamptz not null default now(),
  processed_at timestamptz
);
create index if not exists koja_e2e_webhook_provider_idx on public.koja_e2e_webhook_events(provider,created_at desc);

alter table public.koja_e2e_orders add column if not exists refund_amount numeric(14,2) not null default 0;
alter table public.koja_e2e_orders add column if not exists dispute_status text;
alter table public.koja_e2e_orders add column if not exists reconciled_at timestamptz;
create index if not exists koja_e2e_orders_reconciled_idx on public.koja_e2e_orders(reconciled_at desc);
