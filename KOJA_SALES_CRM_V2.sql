-- KOJA SALES + CRM V1 — additive/update-safe migration
create table if not exists public.koja_sales_leads (id uuid primary key, organization_id uuid, owner_id uuid, name text, company text, email text, phone text, source text, status text default 'new', notes text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.koja_sales_customers (id uuid primary key, organization_id uuid, owner_id uuid, name text, company text, email text, phone text, customer_type text default 'business', status text default 'active', notes text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.koja_sales_opportunities (id uuid primary key, organization_id uuid, owner_id uuid, customer_id uuid, name text, stage text default 'prospecting', probability numeric default 10, expected_value numeric default 0, expected_close_date date, notes text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.koja_sales_quotes (id uuid primary key, organization_id uuid, owner_id uuid, customer_id uuid, quote_number text, title text, total numeric default 0, currency text default 'ZMW', status text default 'draft', valid_until date, notes text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.koja_sales_quote_items (id uuid primary key, quote_id uuid, product_id uuid, description text, quantity numeric default 1, unit_price numeric default 0, total numeric default 0, created_at timestamptz default now());
create table if not exists public.koja_sales_orders (id uuid primary key, organization_id uuid, owner_id uuid, customer_id uuid, quote_id uuid, order_number text, total numeric default 0, currency text default 'ZMW', status text default 'draft', source text default 'crm', notes text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.koja_sales_order_items (id uuid primary key, order_id uuid, product_id uuid, description text, quantity numeric default 1, unit_price numeric default 0, total numeric default 0, created_at timestamptz default now());
create table if not exists public.koja_sales_activities (id uuid primary key, organization_id uuid, owner_id uuid, activity_type text default 'note', subject text, description text, related_type text, related_id uuid, due_at timestamptz, status text default 'open', created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.koja_sales_events (id uuid primary key, organization_id uuid, actor_id uuid, event_type text, entity_type text, entity_id uuid, payload jsonb default '{}'::jsonb, created_at timestamptz default now());

-- Compatibility columns for partial/pre-existing tables
alter table public.koja_sales_leads add column if not exists organization_id uuid; alter table public.koja_sales_leads add column if not exists owner_id uuid; alter table public.koja_sales_leads add column if not exists name text; alter table public.koja_sales_leads add column if not exists company text; alter table public.koja_sales_leads add column if not exists email text; alter table public.koja_sales_leads add column if not exists phone text; alter table public.koja_sales_leads add column if not exists source text; alter table public.koja_sales_leads add column if not exists status text default 'new'; alter table public.koja_sales_leads add column if not exists notes text; alter table public.koja_sales_leads add column if not exists created_at timestamptz default now(); alter table public.koja_sales_leads add column if not exists updated_at timestamptz default now();
alter table public.koja_sales_customers add column if not exists organization_id uuid; alter table public.koja_sales_customers add column if not exists owner_id uuid; alter table public.koja_sales_customers add column if not exists name text; alter table public.koja_sales_customers add column if not exists company text; alter table public.koja_sales_customers add column if not exists email text; alter table public.koja_sales_customers add column if not exists phone text; alter table public.koja_sales_customers add column if not exists customer_type text default 'business'; alter table public.koja_sales_customers add column if not exists status text default 'active'; alter table public.koja_sales_customers add column if not exists notes text; alter table public.koja_sales_customers add column if not exists created_at timestamptz default now(); alter table public.koja_sales_customers add column if not exists updated_at timestamptz default now();
alter table public.koja_sales_opportunities add column if not exists organization_id uuid; alter table public.koja_sales_opportunities add column if not exists owner_id uuid; alter table public.koja_sales_opportunities add column if not exists customer_id uuid; alter table public.koja_sales_opportunities add column if not exists name text; alter table public.koja_sales_opportunities add column if not exists stage text default 'prospecting'; alter table public.koja_sales_opportunities add column if not exists probability numeric default 10; alter table public.koja_sales_opportunities add column if not exists expected_value numeric default 0; alter table public.koja_sales_opportunities add column if not exists expected_close_date date; alter table public.koja_sales_opportunities add column if not exists notes text; alter table public.koja_sales_opportunities add column if not exists created_at timestamptz default now(); alter table public.koja_sales_opportunities add column if not exists updated_at timestamptz default now();
alter table public.koja_sales_quotes add column if not exists organization_id uuid; alter table public.koja_sales_quotes add column if not exists owner_id uuid; alter table public.koja_sales_quotes add column if not exists customer_id uuid; alter table public.koja_sales_quotes add column if not exists quote_number text; alter table public.koja_sales_quotes add column if not exists title text; alter table public.koja_sales_quotes add column if not exists total numeric default 0; alter table public.koja_sales_quotes add column if not exists currency text default 'ZMW'; alter table public.koja_sales_quotes add column if not exists status text default 'draft'; alter table public.koja_sales_quotes add column if not exists valid_until date; alter table public.koja_sales_quotes add column if not exists notes text; alter table public.koja_sales_quotes add column if not exists created_at timestamptz default now(); alter table public.koja_sales_quotes add column if not exists updated_at timestamptz default now();
alter table public.koja_sales_orders add column if not exists organization_id uuid; alter table public.koja_sales_orders add column if not exists owner_id uuid; alter table public.koja_sales_orders add column if not exists customer_id uuid; alter table public.koja_sales_orders add column if not exists quote_id uuid; alter table public.koja_sales_orders add column if not exists order_number text; alter table public.koja_sales_orders add column if not exists total numeric default 0; alter table public.koja_sales_orders add column if not exists currency text default 'ZMW'; alter table public.koja_sales_orders add column if not exists status text default 'draft'; alter table public.koja_sales_orders add column if not exists source text default 'crm'; alter table public.koja_sales_orders add column if not exists notes text; alter table public.koja_sales_orders add column if not exists created_at timestamptz default now(); alter table public.koja_sales_orders add column if not exists updated_at timestamptz default now();
alter table public.koja_sales_activities add column if not exists organization_id uuid; alter table public.koja_sales_activities add column if not exists owner_id uuid; alter table public.koja_sales_activities add column if not exists activity_type text default 'note'; alter table public.koja_sales_activities add column if not exists subject text; alter table public.koja_sales_activities add column if not exists description text; alter table public.koja_sales_activities add column if not exists related_type text; alter table public.koja_sales_activities add column if not exists related_id uuid; alter table public.koja_sales_activities add column if not exists due_at timestamptz; alter table public.koja_sales_activities add column if not exists status text default 'open'; alter table public.koja_sales_activities add column if not exists created_at timestamptz default now(); alter table public.koja_sales_activities add column if not exists updated_at timestamptz default now();

create index if not exists idx_koja_sales_leads_org on public.koja_sales_leads(organization_id);
create index if not exists idx_koja_sales_customers_org on public.koja_sales_customers(organization_id);
create index if not exists idx_koja_sales_opportunities_org_stage on public.koja_sales_opportunities(organization_id, stage);
create index if not exists idx_koja_sales_quotes_org on public.koja_sales_quotes(organization_id);
create index if not exists idx_koja_sales_orders_org on public.koja_sales_orders(organization_id);
create index if not exists idx_koja_sales_activities_org on public.koja_sales_activities(organization_id);
create index if not exists idx_koja_sales_events_org on public.koja_sales_events(organization_id);

-- KOJA SALES + CRM V2 — additive/update-safe completion layer
alter table public.koja_sales_leads add column if not exists lead_score numeric default 0;
alter table public.koja_sales_leads add column if not exists qualification text default 'unqualified';
alter table public.koja_sales_leads add column if not exists converted_customer_id uuid;
alter table public.koja_sales_customers add column if not exists segment text;
alter table public.koja_sales_customers add column if not exists lifetime_value numeric default 0;
alter table public.koja_sales_customers add column if not exists last_contact_at timestamptz;
alter table public.koja_sales_opportunities add column if not exists loss_reason text;
alter table public.koja_sales_opportunities add column if not exists competitor text;
alter table public.koja_sales_opportunities add column if not exists next_step text;
alter table public.koja_sales_opportunities add column if not exists source text;
alter table public.koja_sales_quotes add column if not exists opportunity_id uuid;
alter table public.koja_sales_quotes add column if not exists discount numeric default 0;
alter table public.koja_sales_quotes add column if not exists tax numeric default 0;
alter table public.koja_sales_quotes add column if not exists approval_status text default 'not_required';
alter table public.koja_sales_orders add column if not exists opportunity_id uuid;
alter table public.koja_sales_orders add column if not exists payment_status text default 'unpaid';
alter table public.koja_sales_orders add column if not exists fulfillment_status text default 'pending';
alter table public.koja_sales_orders add column if not exists finance_transaction_id uuid;
alter table public.koja_sales_activities add column if not exists completed_at timestamptz;
alter table public.koja_sales_events add column if not exists source text default 'crm';

create table if not exists public.koja_sales_targets (
 id uuid primary key, organization_id uuid, owner_id uuid, period text, target_amount numeric default 0, currency text default 'ZMW', created_at timestamptz default now(), updated_at timestamptz default now()
);
alter table public.koja_sales_targets add column if not exists organization_id uuid;
alter table public.koja_sales_targets add column if not exists owner_id uuid;
alter table public.koja_sales_targets add column if not exists period text;
alter table public.koja_sales_targets add column if not exists target_amount numeric default 0;
alter table public.koja_sales_targets add column if not exists currency text default 'ZMW';
alter table public.koja_sales_targets add column if not exists created_at timestamptz default now();
alter table public.koja_sales_targets add column if not exists updated_at timestamptz default now();

create index if not exists idx_koja_sales_leads_org_status on public.koja_sales_leads(organization_id,status);
create index if not exists idx_koja_sales_leads_qualification on public.koja_sales_leads(organization_id,qualification);
create index if not exists idx_koja_sales_customers_org_segment on public.koja_sales_customers(organization_id,segment);
create index if not exists idx_koja_sales_opportunities_close on public.koja_sales_opportunities(organization_id,expected_close_date);
create index if not exists idx_koja_sales_quotes_opportunity on public.koja_sales_quotes(opportunity_id);
create index if not exists idx_koja_sales_orders_customer_status on public.koja_sales_orders(organization_id,customer_id,status);
create index if not exists idx_koja_sales_activities_due on public.koja_sales_activities(organization_id,due_at,status);
create index if not exists idx_koja_sales_targets_org_period on public.koja_sales_targets(organization_id,period);
