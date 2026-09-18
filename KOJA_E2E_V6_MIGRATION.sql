-- KOJA AFRICA E2E V6 — Everything Purchasable
-- Additive/update-safe migration. Run after V1, V2, V4 and V5.

create table if not exists public.koja_e2e_checkout_sessions (
    id uuid primary key default gen_random_uuid(),
    order_id uuid not null,
    customer_id uuid not null,
    source_type text not null,
    source_id text,
    tx_ref text not null unique,
    transaction_id text,
    amount numeric(14,2) not null default 0,
    currency text not null default 'ZMW',
    status text not null default 'pending',
    metadata jsonb not null default '{}'::jsonb,
    verified_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_koja_e2e_checkout_customer on public.koja_e2e_checkout_sessions(customer_id, created_at desc);
create index if not exists idx_koja_e2e_checkout_order on public.koja_e2e_checkout_sessions(order_id);
create index if not exists idx_koja_e2e_checkout_source on public.koja_e2e_checkout_sessions(source_type, source_id);
create index if not exists idx_koja_e2e_checkout_status on public.koja_e2e_checkout_sessions(status, created_at desc);

-- Safe additive metadata for future checkout providers and reconciliation.
alter table public.koja_e2e_checkout_sessions add column if not exists provider text default 'flutterwave';
alter table public.koja_e2e_checkout_sessions add column if not exists failure_reason text;

-- Register V6 in the existing module registry when V5 has created it.
insert into public.koja_e2e_module_registry (module_key, module_name, description, enabled, metadata, created_at, updated_at)
select 'everything_purchasable', 'Everything Purchasable',
       'Customer-facing purchase and booking layer for Business POS products, professional services and published E2E services.',
       true, '{"version":"2026.09.18-V6","connect_plus":"untouched"}'::jsonb, now(), now()
where to_regclass('public.koja_e2e_module_registry') is not null
  and not exists (select 1 from public.koja_e2e_module_registry where module_key='everything_purchasable');
