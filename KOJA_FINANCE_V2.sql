-- KOJA FINANCE V2 — additive/update-safe migration
-- No DROP/TRUNCATE/RECREATE of existing KOJA tables.

create table if not exists public.koja_finance_v2_accounts (
  id uuid primary key, user_id uuid, organization_id uuid, code text, name text,
  account_type text, currency text default 'ZMW', description text, status text default 'active',
  created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table public.koja_finance_v2_accounts add column if not exists user_id uuid;
alter table public.koja_finance_v2_accounts add column if not exists organization_id uuid;
alter table public.koja_finance_v2_accounts add column if not exists code text;
alter table public.koja_finance_v2_accounts add column if not exists name text;
alter table public.koja_finance_v2_accounts add column if not exists account_type text;
alter table public.koja_finance_v2_accounts add column if not exists currency text default 'ZMW';
alter table public.koja_finance_v2_accounts add column if not exists description text;
alter table public.koja_finance_v2_accounts add column if not exists status text default 'active';
alter table public.koja_finance_v2_accounts add column if not exists created_at timestamptz default now();
alter table public.koja_finance_v2_accounts add column if not exists updated_at timestamptz default now();

create table if not exists public.koja_finance_v2_journal_entries (
  id uuid primary key, user_id uuid, organization_id uuid, entry_number text, description text,
  reference text, currency text default 'ZMW', total_debit numeric(18,2) default 0,
  total_credit numeric(18,2) default 0, status text default 'posted', entry_date date,
  created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table public.koja_finance_v2_journal_entries add column if not exists user_id uuid;
alter table public.koja_finance_v2_journal_entries add column if not exists organization_id uuid;
alter table public.koja_finance_v2_journal_entries add column if not exists entry_number text;
alter table public.koja_finance_v2_journal_entries add column if not exists description text;
alter table public.koja_finance_v2_journal_entries add column if not exists reference text;
alter table public.koja_finance_v2_journal_entries add column if not exists currency text default 'ZMW';
alter table public.koja_finance_v2_journal_entries add column if not exists total_debit numeric(18,2) default 0;
alter table public.koja_finance_v2_journal_entries add column if not exists total_credit numeric(18,2) default 0;
alter table public.koja_finance_v2_journal_entries add column if not exists status text default 'posted';
alter table public.koja_finance_v2_journal_entries add column if not exists entry_date date;
alter table public.koja_finance_v2_journal_entries add column if not exists created_at timestamptz default now();
alter table public.koja_finance_v2_journal_entries add column if not exists updated_at timestamptz default now();

create table if not exists public.koja_finance_v2_journal_lines (
  id uuid primary key, journal_entry_id uuid, account_id uuid, line_type text,
  amount numeric(18,2) default 0, description text, created_at timestamptz default now()
);
alter table public.koja_finance_v2_journal_lines add column if not exists journal_entry_id uuid;
alter table public.koja_finance_v2_journal_lines add column if not exists account_id uuid;
alter table public.koja_finance_v2_journal_lines add column if not exists line_type text;
alter table public.koja_finance_v2_journal_lines add column if not exists amount numeric(18,2) default 0;
alter table public.koja_finance_v2_journal_lines add column if not exists description text;
alter table public.koja_finance_v2_journal_lines add column if not exists created_at timestamptz default now();

create table if not exists public.koja_finance_v2_payments (
  id uuid primary key, user_id uuid, organization_id uuid, payment_number text, direction text,
  party_name text, amount numeric(18,2) default 0, currency text default 'ZMW', method text,
  status text default 'completed', reference text, payment_date date, source_type text, source_id text,
  created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table public.koja_finance_v2_payments add column if not exists user_id uuid;
alter table public.koja_finance_v2_payments add column if not exists organization_id uuid;
alter table public.koja_finance_v2_payments add column if not exists payment_number text;
alter table public.koja_finance_v2_payments add column if not exists direction text;
alter table public.koja_finance_v2_payments add column if not exists party_name text;
alter table public.koja_finance_v2_payments add column if not exists amount numeric(18,2) default 0;
alter table public.koja_finance_v2_payments add column if not exists currency text default 'ZMW';
alter table public.koja_finance_v2_payments add column if not exists method text;
alter table public.koja_finance_v2_payments add column if not exists status text default 'completed';
alter table public.koja_finance_v2_payments add column if not exists reference text;
alter table public.koja_finance_v2_payments add column if not exists payment_date date;
alter table public.koja_finance_v2_payments add column if not exists source_type text;
alter table public.koja_finance_v2_payments add column if not exists source_id text;
alter table public.koja_finance_v2_payments add column if not exists created_at timestamptz default now();
alter table public.koja_finance_v2_payments add column if not exists updated_at timestamptz default now();

create table if not exists public.koja_finance_v2_bank_accounts (
  id uuid primary key, user_id uuid, organization_id uuid, name text, bank_name text,
  account_number_masked text, currency text default 'ZMW', opening_balance numeric(18,2) default 0,
  status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table public.koja_finance_v2_bank_accounts add column if not exists user_id uuid;
alter table public.koja_finance_v2_bank_accounts add column if not exists organization_id uuid;
alter table public.koja_finance_v2_bank_accounts add column if not exists name text;
alter table public.koja_finance_v2_bank_accounts add column if not exists bank_name text;
alter table public.koja_finance_v2_bank_accounts add column if not exists account_number_masked text;
alter table public.koja_finance_v2_bank_accounts add column if not exists currency text default 'ZMW';
alter table public.koja_finance_v2_bank_accounts add column if not exists opening_balance numeric(18,2) default 0;
alter table public.koja_finance_v2_bank_accounts add column if not exists status text default 'active';
alter table public.koja_finance_v2_bank_accounts add column if not exists created_at timestamptz default now();
alter table public.koja_finance_v2_bank_accounts add column if not exists updated_at timestamptz default now();

create table if not exists public.koja_finance_v2_budgets (
  id uuid primary key, user_id uuid, organization_id uuid, name text, period_start date, period_end date,
  currency text default 'ZMW', amount numeric(18,2) default 0, status text default 'active',
  created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table public.koja_finance_v2_budgets add column if not exists user_id uuid;
alter table public.koja_finance_v2_budgets add column if not exists organization_id uuid;
alter table public.koja_finance_v2_budgets add column if not exists name text;
alter table public.koja_finance_v2_budgets add column if not exists period_start date;
alter table public.koja_finance_v2_budgets add column if not exists period_end date;
alter table public.koja_finance_v2_budgets add column if not exists currency text default 'ZMW';
alter table public.koja_finance_v2_budgets add column if not exists amount numeric(18,2) default 0;
alter table public.koja_finance_v2_budgets add column if not exists status text default 'active';
alter table public.koja_finance_v2_budgets add column if not exists created_at timestamptz default now();
alter table public.koja_finance_v2_budgets add column if not exists updated_at timestamptz default now();

create table if not exists public.koja_finance_v2_budget_lines (
  id uuid primary key, budget_id uuid, account_id uuid, amount numeric(18,2) default 0,
  period text, notes text, created_at timestamptz default now()
);
alter table public.koja_finance_v2_budget_lines add column if not exists budget_id uuid;
alter table public.koja_finance_v2_budget_lines add column if not exists account_id uuid;
alter table public.koja_finance_v2_budget_lines add column if not exists amount numeric(18,2) default 0;
alter table public.koja_finance_v2_budget_lines add column if not exists period text;
alter table public.koja_finance_v2_budget_lines add column if not exists notes text;
alter table public.koja_finance_v2_budget_lines add column if not exists created_at timestamptz default now();

create table if not exists public.koja_finance_v2_tax_records (
  id uuid primary key, user_id uuid, organization_id uuid, tax_type text, period text,
  direction text, amount numeric(18,2) default 0, currency text default 'ZMW', status text default 'open',
  reference text, due_date date, created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table public.koja_finance_v2_tax_records add column if not exists user_id uuid;
alter table public.koja_finance_v2_tax_records add column if not exists organization_id uuid;
alter table public.koja_finance_v2_tax_records add column if not exists tax_type text;
alter table public.koja_finance_v2_tax_records add column if not exists period text;
alter table public.koja_finance_v2_tax_records add column if not exists direction text;
alter table public.koja_finance_v2_tax_records add column if not exists amount numeric(18,2) default 0;
alter table public.koja_finance_v2_tax_records add column if not exists currency text default 'ZMW';
alter table public.koja_finance_v2_tax_records add column if not exists status text default 'open';
alter table public.koja_finance_v2_tax_records add column if not exists reference text;
alter table public.koja_finance_v2_tax_records add column if not exists due_date date;
alter table public.koja_finance_v2_tax_records add column if not exists created_at timestamptz default now();
alter table public.koja_finance_v2_tax_records add column if not exists updated_at timestamptz default now();

create table if not exists public.koja_finance_v2_reconciliations (
  id uuid primary key, user_id uuid, organization_id uuid, bank_account_id uuid, period text,
  statement_balance numeric(18,2) default 0, ledger_balance numeric(18,2) default 0,
  difference numeric(18,2) default 0, status text default 'open', notes text,
  created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table public.koja_finance_v2_reconciliations add column if not exists user_id uuid;
alter table public.koja_finance_v2_reconciliations add column if not exists organization_id uuid;
alter table public.koja_finance_v2_reconciliations add column if not exists bank_account_id uuid;
alter table public.koja_finance_v2_reconciliations add column if not exists period text;
alter table public.koja_finance_v2_reconciliations add column if not exists statement_balance numeric(18,2) default 0;
alter table public.koja_finance_v2_reconciliations add column if not exists ledger_balance numeric(18,2) default 0;
alter table public.koja_finance_v2_reconciliations add column if not exists difference numeric(18,2) default 0;
alter table public.koja_finance_v2_reconciliations add column if not exists status text default 'open';
alter table public.koja_finance_v2_reconciliations add column if not exists notes text;
alter table public.koja_finance_v2_reconciliations add column if not exists created_at timestamptz default now();
alter table public.koja_finance_v2_reconciliations add column if not exists updated_at timestamptz default now();

create table if not exists public.koja_finance_v2_periods (
  id uuid primary key, user_id uuid, organization_id uuid, period_code text, start_date date,
  end_date date, status text default 'open', closed_at timestamptz, created_at timestamptz default now()
);
alter table public.koja_finance_v2_periods add column if not exists user_id uuid;
alter table public.koja_finance_v2_periods add column if not exists organization_id uuid;
alter table public.koja_finance_v2_periods add column if not exists period_code text;
alter table public.koja_finance_v2_periods add column if not exists start_date date;
alter table public.koja_finance_v2_periods add column if not exists end_date date;
alter table public.koja_finance_v2_periods add column if not exists status text default 'open';
alter table public.koja_finance_v2_periods add column if not exists closed_at timestamptz;
alter table public.koja_finance_v2_periods add column if not exists created_at timestamptz default now();

create table if not exists public.koja_finance_v2_transactions (
  id uuid primary key, user_id uuid, organization_id uuid, source_type text, source_id text,
  transaction_type text, amount numeric(18,2) default 0, currency text default 'ZMW',
  status text default 'recorded', occurred_at timestamptz, metadata jsonb, created_at timestamptz default now()
);
alter table public.koja_finance_v2_transactions add column if not exists user_id uuid;
alter table public.koja_finance_v2_transactions add column if not exists organization_id uuid;
alter table public.koja_finance_v2_transactions add column if not exists source_type text;
alter table public.koja_finance_v2_transactions add column if not exists source_id text;
alter table public.koja_finance_v2_transactions add column if not exists transaction_type text;
alter table public.koja_finance_v2_transactions add column if not exists amount numeric(18,2) default 0;
alter table public.koja_finance_v2_transactions add column if not exists currency text default 'ZMW';
alter table public.koja_finance_v2_transactions add column if not exists status text default 'recorded';
alter table public.koja_finance_v2_transactions add column if not exists occurred_at timestamptz;
alter table public.koja_finance_v2_transactions add column if not exists metadata jsonb;
alter table public.koja_finance_v2_transactions add column if not exists created_at timestamptz default now();

create table if not exists public.koja_finance_v2_events (
  id uuid primary key, user_id uuid, organization_id uuid, event_type text, entity_type text,
  entity_id text, data jsonb, created_at timestamptz default now()
);
alter table public.koja_finance_v2_events add column if not exists user_id uuid;
alter table public.koja_finance_v2_events add column if not exists organization_id uuid;
alter table public.koja_finance_v2_events add column if not exists event_type text;
alter table public.koja_finance_v2_events add column if not exists entity_type text;
alter table public.koja_finance_v2_events add column if not exists entity_id text;
alter table public.koja_finance_v2_events add column if not exists data jsonb;
alter table public.koja_finance_v2_events add column if not exists created_at timestamptz default now();

create index if not exists idx_kf2_accounts_user on public.koja_finance_v2_accounts(user_id);
create index if not exists idx_kf2_accounts_org on public.koja_finance_v2_accounts(organization_id);
create index if not exists idx_kf2_journal_user on public.koja_finance_v2_journal_entries(user_id);
create index if not exists idx_kf2_journal_org on public.koja_finance_v2_journal_entries(organization_id);
create index if not exists idx_kf2_lines_entry on public.koja_finance_v2_journal_lines(journal_entry_id);
create index if not exists idx_kf2_lines_account on public.koja_finance_v2_journal_lines(account_id);
create index if not exists idx_kf2_payments_user on public.koja_finance_v2_payments(user_id);
create index if not exists idx_kf2_payments_source on public.koja_finance_v2_payments(source_type,source_id);
create index if not exists idx_kf2_budgets_user on public.koja_finance_v2_budgets(user_id);
create index if not exists idx_kf2_tax_user on public.koja_finance_v2_tax_records(user_id);
create index if not exists idx_kf2_recon_user on public.koja_finance_v2_reconciliations(user_id);
create index if not exists idx_kf2_period_user on public.koja_finance_v2_periods(user_id);
create index if not exists idx_kf2_tx_source on public.koja_finance_v2_transactions(source_type,source_id);
create index if not exists idx_kf2_events_user on public.koja_finance_v2_events(user_id);

-- RLS is enabled only for new V2 tables. Existing KOJA tables are untouched.
alter table public.koja_finance_v2_accounts enable row level security;
alter table public.koja_finance_v2_journal_entries enable row level security;
alter table public.koja_finance_v2_journal_lines enable row level security;
alter table public.koja_finance_v2_payments enable row level security;
alter table public.koja_finance_v2_bank_accounts enable row level security;
alter table public.koja_finance_v2_budgets enable row level security;
alter table public.koja_finance_v2_budget_lines enable row level security;
alter table public.koja_finance_v2_tax_records enable row level security;
alter table public.koja_finance_v2_reconciliations enable row level security;
alter table public.koja_finance_v2_periods enable row level security;
alter table public.koja_finance_v2_transactions enable row level security;
alter table public.koja_finance_v2_events enable row level security;

-- Service-role REST access is used by the Flask application. These policies also
-- permit authenticated users to access only rows carrying their auth.uid().
do $$
begin
  execute 'drop policy if exists kf2_accounts_owner on public.koja_finance_v2_accounts';
  execute 'create policy kf2_accounts_owner on public.koja_finance_v2_accounts for all using (auth.uid() = user_id) with check (auth.uid() = user_id)';
  execute 'drop policy if exists kf2_journal_owner on public.koja_finance_v2_journal_entries';
  execute 'create policy kf2_journal_owner on public.koja_finance_v2_journal_entries for all using (auth.uid() = user_id) with check (auth.uid() = user_id)';
  execute 'drop policy if exists kf2_payments_owner on public.koja_finance_v2_payments';
  execute 'create policy kf2_payments_owner on public.koja_finance_v2_payments for all using (auth.uid() = user_id) with check (auth.uid() = user_id)';
  execute 'drop policy if exists kf2_budgets_owner on public.koja_finance_v2_budgets';
  execute 'create policy kf2_budgets_owner on public.koja_finance_v2_budgets for all using (auth.uid() = user_id) with check (auth.uid() = user_id)';
  execute 'drop policy if exists kf2_tax_owner on public.koja_finance_v2_tax_records';
  execute 'create policy kf2_tax_owner on public.koja_finance_v2_tax_records for all using (auth.uid() = user_id) with check (auth.uid() = user_id)';
  execute 'drop policy if exists kf2_recon_owner on public.koja_finance_v2_reconciliations';
  execute 'create policy kf2_recon_owner on public.koja_finance_v2_reconciliations for all using (auth.uid() = user_id) with check (auth.uid() = user_id)';
  execute 'drop policy if exists kf2_period_owner on public.koja_finance_v2_periods';
  execute 'create policy kf2_period_owner on public.koja_finance_v2_periods for all using (auth.uid() = user_id) with check (auth.uid() = user_id)';
  execute 'drop policy if exists kf2_tx_owner on public.koja_finance_v2_transactions';
  execute 'create policy kf2_tx_owner on public.koja_finance_v2_transactions for all using (auth.uid() = user_id) with check (auth.uid() = user_id)';
  execute 'drop policy if exists kf2_events_owner on public.koja_finance_v2_events';
  execute 'create policy kf2_events_owner on public.koja_finance_v2_events for all using (auth.uid() = user_id) with check (auth.uid() = user_id)';
exception when others then
  raise notice 'KOJA Finance V2 policy creation notice: %', SQLERRM;
end $$;
