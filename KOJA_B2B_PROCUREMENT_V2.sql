-- KOJA AFRICA — ADDITIVE B2B + PROCUREMENT V2
-- Safe migration: adds compatibility columns/indexes only. No DROP/RECREATE.

create extension if not exists pgcrypto;

alter table if exists public.koja_b2b_suppliers
  add column if not exists verification_status text default 'pending';

alter table if exists public.koja_b2b_suppliers
  add column if not exists updated_at timestamptz default now();

alter table if exists public.koja_b2b_quotations
  add column if not exists reviewed_by uuid;

alter table if exists public.koja_b2b_quotations
  add column if not exists reviewed_at timestamptz;

alter table if exists public.koja_b2b_quotations
  add column if not exists terms text;

alter table if exists public.koja_b2b_purchase_orders
  add column if not exists approval_status text default 'pending';

alter table if exists public.koja_b2b_purchase_orders
  add column if not exists expected_delivery_date date;

alter table if exists public.koja_b2b_recurring_procurement
  add column if not exists next_run_at timestamptz;

alter table if exists public.koja_b2b_recurring_procurement
  add column if not exists updated_at timestamptz default now();

create index if not exists idx_koja_b2b_quotations_status on public.koja_b2b_quotations(status);
create index if not exists idx_koja_b2b_quotations_supplier on public.koja_b2b_quotations(supplier_id);
create index if not exists idx_koja_b2b_po_quotation on public.koja_b2b_purchase_orders(quotation_id);
create index if not exists idx_koja_b2b_recurring_next_run on public.koja_b2b_recurring_procurement(next_run_at);

-- Keep existing RLS configuration. Flask accesses these tables server-side.
