-- KOJA FINANCE V2 -> PLATFORM FOUNDATIONS V2
-- Additive integration migration. Run after KOJA_PLATFORM_FOUNDATIONS_V2.sql.
-- No DROP, TRUNCATE, or table recreation.

create extension if not exists pgcrypto;

alter table if exists public.koja_finance_v2_payments
  add column if not exists foundation_transaction_id uuid;
alter table if exists public.koja_finance_v2_journal_entries
  add column if not exists foundation_transaction_id uuid;
alter table if exists public.koja_finance_v2_reconciliations
  add column if not exists platform_event_id uuid;
alter table if exists public.koja_finance_v2_transactions
  add column if not exists foundation_transaction_id uuid;

create index if not exists idx_koja_finance_payments_foundation_tx
  on public.koja_finance_v2_payments(foundation_transaction_id);
create index if not exists idx_koja_finance_journal_foundation_tx
  on public.koja_finance_v2_journal_entries(foundation_transaction_id);
create index if not exists idx_koja_finance_reconciliation_platform_event
  on public.koja_finance_v2_reconciliations(platform_event_id);
create index if not exists idx_koja_finance_transactions_foundation_tx
  on public.koja_finance_v2_transactions(foundation_transaction_id);

-- Flask writes canonical records to:
--   koja_platform_events
--   koja_unified_transactions
--   koja_engine_revenue (for completed inbound payments)
-- with service_key = 'finance'.
-- The source-table IDs above provide additive traceability for future reconciliation.
