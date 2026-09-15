-- KOJA AFRICA — ADDITIVE ENTERPRISE V1
-- Safe migration: CREATE TABLE IF NOT EXISTS only. Existing KOJA tables are untouched.
create extension if not exists pgcrypto;

create table if not exists public.koja_enterprise_departments (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
 name text not null, code text, head_user_id uuid, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_employees (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
 user_id uuid, department_id uuid references public.koja_enterprise_departments(id) on delete set null,
 full_name text not null, email text, job_title text, employment_status text default 'active', hired_at date,
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_roles (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
 name text not null, description text, permissions jsonb default '[]'::jsonb, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_role_members (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
 role_id uuid references public.koja_enterprise_roles(id) on delete cascade, user_id uuid, employee_id uuid references public.koja_enterprise_employees(id) on delete cascade,
 created_at timestamptz default now(), unique(role_id,user_id)
);
create table if not exists public.koja_enterprise_workspaces (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
 name text not null, description text, owner_id uuid, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_contracts (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
 contract_number text, title text not null, counterparty text, start_date date, end_date date,
 value numeric(18,2) default 0, currency text default 'ZMW', status text default 'draft', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_approvals (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
 requested_by uuid, approver_id uuid, title text not null, entity_type text, entity_id uuid, status text default 'pending', notes text,
 decided_at timestamptz, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_documents (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
 owner_id uuid, title text not null, document_type text default 'general', file_url text, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_billing (
 id uuid primary key default gen_random_uuid(), organization_id uuid references public.koja_b2b_organizations(id) on delete cascade,
 description text not null, billing_type text default 'subscription', amount numeric(18,2) default 0, currency text default 'ZMW', status text default 'pending', due_at timestamptz,
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_events (
 id uuid primary key default gen_random_uuid(), organization_id uuid, actor_id uuid, event_type text not null, entity_type text, entity_id uuid, payload jsonb default '{}'::jsonb, created_at timestamptz default now()
);

create index if not exists idx_koja_ent_dept_org on public.koja_enterprise_departments(organization_id);
create index if not exists idx_koja_ent_emp_org on public.koja_enterprise_employees(organization_id);
create index if not exists idx_koja_ent_emp_dept on public.koja_enterprise_employees(department_id);
create index if not exists idx_koja_ent_roles_org on public.koja_enterprise_roles(organization_id);
create index if not exists idx_koja_ent_role_members_org on public.koja_enterprise_role_members(organization_id);
create index if not exists idx_koja_ent_workspace_org on public.koja_enterprise_workspaces(organization_id);
create index if not exists idx_koja_ent_contract_org on public.koja_enterprise_contracts(organization_id);
create index if not exists idx_koja_ent_approval_org_status on public.koja_enterprise_approvals(organization_id,status);
create index if not exists idx_koja_ent_docs_org on public.koja_enterprise_documents(organization_id);
create index if not exists idx_koja_ent_billing_org on public.koja_enterprise_billing(organization_id);
create index if not exists idx_koja_ent_events_entity on public.koja_enterprise_events(entity_type,entity_id);

alter table public.koja_enterprise_departments enable row level security;
alter table public.koja_enterprise_employees enable row level security;
alter table public.koja_enterprise_roles enable row level security;
alter table public.koja_enterprise_role_members enable row level security;
alter table public.koja_enterprise_workspaces enable row level security;
alter table public.koja_enterprise_contracts enable row level security;
alter table public.koja_enterprise_approvals enable row level security;
alter table public.koja_enterprise_documents enable row level security;
alter table public.koja_enterprise_billing enable row level security;
alter table public.koja_enterprise_events enable row level security;

-- Server-side Flask uses Supabase REST with the service role. No browser policies are added here.
