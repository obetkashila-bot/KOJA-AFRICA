-- KOJA AFRICA End-to-End V2 — additive migration only
create extension if not exists pgcrypto;
create table if not exists public.koja_e2e_source_links (
 id uuid primary key default gen_random_uuid(), source_type text not null, source_id text not null,
 service_id uuid, order_id uuid, metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(source_type, source_id)
);
create index if not exists idx_koja_e2e_source_links_order on public.koja_e2e_source_links(order_id);
create index if not exists idx_koja_e2e_source_links_service on public.koja_e2e_source_links(service_id);
alter table public.koja_e2e_orders add column if not exists source_type text;
alter table public.koja_e2e_orders add column if not exists source_id text;
alter table public.koja_e2e_orders add column if not exists metadata jsonb not null default '{}'::jsonb;
create index if not exists idx_koja_e2e_orders_source on public.koja_e2e_orders(source_type,source_id);
alter table public.koja_e2e_services add column if not exists source_type text;
alter table public.koja_e2e_services add column if not exists source_id text;
alter table public.koja_e2e_services add column if not exists metadata jsonb not null default '{}'::jsonb;
create index if not exists idx_koja_e2e_services_source on public.koja_e2e_services(source_type,source_id);
