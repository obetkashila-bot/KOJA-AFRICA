-- KOJA ENTERPRISE V2 — additive/update-safe foundation + governance layer
-- No DROP, TRUNCATE or table recreation.
create extension if not exists pgcrypto;

-- Shared organization foundation used by KOJA B2B / Enterprise.
create table if not exists public.koja_b2b_organizations (
 id uuid primary key,
 owner_id uuid,
 name text,
 legal_name text,
 country text default 'ZM',
 currency text default 'ZMW',
 status text default 'active',
 created_at timestamptz default now(),
 updated_at timestamptz default now()
);
alter table public.koja_b2b_organizations add column if not exists owner_id uuid;
alter table public.koja_b2b_organizations add column if not exists name text;
alter table public.koja_b2b_organizations add column if not exists legal_name text;
alter table public.koja_b2b_organizations add column if not exists country text default 'ZM';
alter table public.koja_b2b_organizations add column if not exists currency text default 'ZMW';
alter table public.koja_b2b_organizations add column if not exists status text default 'active';
alter table public.koja_b2b_organizations add column if not exists created_at timestamptz default now();
alter table public.koja_b2b_organizations add column if not exists updated_at timestamptz default now();

create table if not exists public.koja_b2b_members (
 id uuid primary key,
 organization_id uuid,
 user_id uuid,
 role text default 'member',
 status text default 'active',
 created_at timestamptz default now(),
 updated_at timestamptz default now()
);
alter table public.koja_b2b_members add column if not exists organization_id uuid;
alter table public.koja_b2b_members add column if not exists user_id uuid;
alter table public.koja_b2b_members add column if not exists role text default 'member';
alter table public.koja_b2b_members add column if not exists status text default 'active';
alter table public.koja_b2b_members add column if not exists created_at timestamptz default now();
alter table public.koja_b2b_members add column if not exists updated_at timestamptz default now();

-- Enterprise V1 foundation, created safely if the earlier migration was not installed.
create table if not exists public.koja_enterprise_departments (
 id uuid primary key, organization_id uuid, name text, code text, head_user_id uuid, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_employees (
 id uuid primary key, organization_id uuid, user_id uuid, full_name text, email text, job_title text, department_id uuid, employment_status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_roles (
 id uuid primary key, organization_id uuid, name text, description text, permissions jsonb default '[]'::jsonb, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_role_members (
 id uuid primary key, organization_id uuid, role_id uuid, user_id uuid, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_workspaces (
 id uuid primary key, organization_id uuid, name text, description text, owner_id uuid, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_contracts (
 id uuid primary key, organization_id uuid, contract_number text, title text, counterparty text, start_date date, end_date date, value numeric default 0, currency text default 'ZMW', status text default 'draft', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_approvals (
 id uuid primary key, organization_id uuid, requested_by uuid, title text, entity_type text, entity_id uuid, status text default 'pending', notes text, approved_by uuid, decision_at timestamptz, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_documents (
 id uuid primary key, organization_id uuid, owner_id uuid, title text, document_type text default 'general', file_url text, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_billing (
 id uuid primary key, organization_id uuid, description text, amount numeric default 0, currency text default 'ZMW', billing_type text default 'subscription', status text default 'pending', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_events (
 id uuid primary key, organization_id uuid, actor_id uuid, event_type text, entity_type text, entity_id uuid, metadata jsonb default '{}'::jsonb, created_at timestamptz default now()
);

-- Compatibility columns for existing Enterprise V1 tables.
alter table public.koja_enterprise_approvals add column if not exists approved_by uuid;
alter table public.koja_enterprise_approvals add column if not exists decision_at timestamptz;
alter table public.koja_enterprise_events add column if not exists metadata jsonb default '{}'::jsonb;

-- Enterprise V2 governance and multi-location layer.
create table if not exists public.koja_enterprise_locations (
 id uuid primary key, organization_id uuid, name text, code text, country text default 'ZM', city text, address text, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_teams (
 id uuid primary key, organization_id uuid, name text, description text, department_id uuid, leader_user_id uuid, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_team_members (
 id uuid primary key, organization_id uuid, team_id uuid, user_id uuid, role text default 'member', status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_invitations (
 id uuid primary key, organization_id uuid, email text, role text default 'member', invited_by uuid, status text default 'pending', expires_at timestamptz, accepted_at timestamptz, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_settings (
 id uuid primary key, organization_id uuid unique, timezone text default 'Africa/Lusaka', default_currency text default 'ZMW', fiscal_year_start_month integer default 1, settings jsonb default '{}'::jsonb, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_enterprise_access_policies (
 id uuid primary key, organization_id uuid, name text, resource text, action text, effect text default 'allow', role_name text, conditions jsonb default '{}'::jsonb, status text default 'active', created_at timestamptz default now(), updated_at timestamptz default now()
);

-- Additive columns for future governance workflows.
alter table public.koja_enterprise_locations add column if not exists organization_id uuid;
alter table public.koja_enterprise_locations add column if not exists name text;
alter table public.koja_enterprise_locations add column if not exists code text;
alter table public.koja_enterprise_locations add column if not exists country text default 'ZM';
alter table public.koja_enterprise_locations add column if not exists city text;
alter table public.koja_enterprise_locations add column if not exists address text;
alter table public.koja_enterprise_locations add column if not exists status text default 'active';
alter table public.koja_enterprise_locations add column if not exists created_at timestamptz default now();
alter table public.koja_enterprise_locations add column if not exists updated_at timestamptz default now();

alter table public.koja_enterprise_teams add column if not exists organization_id uuid;
alter table public.koja_enterprise_teams add column if not exists name text;
alter table public.koja_enterprise_teams add column if not exists description text;
alter table public.koja_enterprise_teams add column if not exists department_id uuid;
alter table public.koja_enterprise_teams add column if not exists leader_user_id uuid;
alter table public.koja_enterprise_teams add column if not exists status text default 'active';
alter table public.koja_enterprise_teams add column if not exists created_at timestamptz default now();
alter table public.koja_enterprise_teams add column if not exists updated_at timestamptz default now();

create index if not exists idx_koja_b2b_org_owner on public.koja_b2b_organizations(owner_id);
create index if not exists idx_koja_b2b_members_org_user on public.koja_b2b_members(organization_id,user_id);
create index if not exists idx_koja_enterprise_departments_org on public.koja_enterprise_departments(organization_id);
create index if not exists idx_koja_enterprise_employees_org on public.koja_enterprise_employees(organization_id);
create index if not exists idx_koja_enterprise_roles_org on public.koja_enterprise_roles(organization_id);
create index if not exists idx_koja_enterprise_role_members_org on public.koja_enterprise_role_members(organization_id,user_id);
create index if not exists idx_koja_enterprise_workspaces_org on public.koja_enterprise_workspaces(organization_id);
create index if not exists idx_koja_enterprise_contracts_org_status on public.koja_enterprise_contracts(organization_id,status);
create index if not exists idx_koja_enterprise_approvals_org_status on public.koja_enterprise_approvals(organization_id,status);
create index if not exists idx_koja_enterprise_documents_org on public.koja_enterprise_documents(organization_id);
create index if not exists idx_koja_enterprise_billing_org_status on public.koja_enterprise_billing(organization_id,status);
create index if not exists idx_koja_enterprise_events_org_created on public.koja_enterprise_events(organization_id,created_at desc);
create index if not exists idx_koja_enterprise_locations_org on public.koja_enterprise_locations(organization_id);
create index if not exists idx_koja_enterprise_teams_org on public.koja_enterprise_teams(organization_id);
create index if not exists idx_koja_enterprise_team_members_org_team on public.koja_enterprise_team_members(organization_id,team_id);
create index if not exists idx_koja_enterprise_invitations_org_status on public.koja_enterprise_invitations(organization_id,status);
create index if not exists idx_koja_enterprise_policies_org on public.koja_enterprise_access_policies(organization_id);
