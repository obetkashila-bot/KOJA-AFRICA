-- KOJA AFRICA Production Hardening V2
-- SAFE / ADDITIVE / IDEMPOTENT. Does not drop, recreate, truncate or delete existing business data.

create extension if not exists pgcrypto;

create table if not exists public.koja_idempotency_keys_v2 (
  id uuid primary key default gen_random_uuid(),
  idempotency_key text not null,
  scope text not null,
  user_id uuid,
  request_hash text not null default '',
  status text not null default 'processing',
  response_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (idempotency_key, scope)
);
create index if not exists koja_idempotency_user_idx on public.koja_idempotency_keys_v2(user_id, created_at desc);
create index if not exists koja_idempotency_status_idx on public.koja_idempotency_keys_v2(status, updated_at desc);

alter table if exists public.koja_market_payouts add column if not exists processed_at timestamptz;
alter table if exists public.koja_market_payouts add column if not exists failure_reason text;

alter table if exists public.deliveries add column if not exists rejection_count integer not null default 0;
alter table if exists public.deliveries add column if not exists last_reassigned_at timestamptz;

-- Keep the audit table usable for the hardening layer even when an earlier migration created it.
alter table if exists public.koja_audit_log_v2 add column if not exists metadata jsonb not null default '{}'::jsonb;
alter table if exists public.koja_audit_log_v2 add column if not exists created_at timestamptz not null default now();

-- Cleanup helper for stale idempotency records. Safe to run manually or from a scheduled job.
create or replace function public.koja_cleanup_idempotency_v2(retention_days integer default 7)
returns integer
language plpgsql
security definer
as $$
declare
  deleted_count integer;
begin
  delete from public.koja_idempotency_keys_v2
  where created_at < now() - make_interval(days => greatest(retention_days, 1));
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

-- Verification
select 'koja_idempotency_keys_v2' as table_name, to_regclass('public.koja_idempotency_keys_v2') is not null as installed
union all
select 'koja_market_payouts.processed_at', exists(select 1 from information_schema.columns where table_schema='public' and table_name='koja_market_payouts' and column_name='processed_at')
union all
select 'deliveries.rejection_count', exists(select 1 from information_schema.columns where table_schema='public' and table_name='deliveries' and column_name='rejection_count')
union all
select 'koja_audit_log_v2.metadata', exists(select 1 from information_schema.columns where table_schema='public' and table_name='koja_audit_log_v2' and column_name='metadata');
