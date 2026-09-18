-- KOJA AFRICA E2E V5
-- Additive / update-safe. Does not recreate or delete existing tables.

create table if not exists public.koja_e2e_automation_events (
  id uuid primary key default gen_random_uuid(),
  source_type text not null,
  source_id text not null,
  action text not null,
  source_status text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists koja_e2e_auto_source_idx
  on public.koja_e2e_automation_events(source_type, source_id, created_at desc);

create index if not exists koja_e2e_auto_action_idx
  on public.koja_e2e_automation_events(action, created_at desc);

alter table public.koja_e2e_source_links
  add column if not exists last_synced_at timestamptz;

alter table public.koja_e2e_source_links
  add column if not exists sync_status text default 'active';

alter table public.koja_e2e_source_links
  add column if not exists metadata jsonb not null default '{}'::jsonb;

create index if not exists koja_e2e_source_links_sync_idx
  on public.koja_e2e_source_links(sync_status, last_synced_at desc);

-- Optional registry for future modules. It is intentionally independent of
-- existing service tables so V5 remains additive and safe.
create table if not exists public.koja_e2e_module_registry (
  module_key text primary key,
  display_name text not null,
  enabled boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.koja_e2e_module_registry(module_key,display_name,enabled,metadata)
values
 ('market','KOJA Market',true,'{}'::jsonb),
 ('business','KOJA Business',true,'{}'::jsonb),
 ('professional','Professional Services',true,'{}'::jsonb),
 ('b2b','KOJA B2B',true,'{}'::jsonb),
 ('global_trade','Global Import & Export',true,'{}'::jsonb),
 ('business_store','Business Online Store',true,'{}'::jsonb),
 ('business_live','Business Live / Training',true,'{}'::jsonb),
 ('ai_credits','KOJA AI Credits',true,'{}'::jsonb),
 ('delivery','KOJA Delivery',true,'{}'::jsonb)
on conflict (module_key) do update set display_name=excluded.display_name, updated_at=now();
