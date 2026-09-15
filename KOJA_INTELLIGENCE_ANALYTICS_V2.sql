-- KOJA INTELLIGENCE & ANALYTICS V2
-- Additive/update-safe migration. No existing table is dropped or recreated.
create table if not exists public.koja_intelligence_v2_metrics (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 organization_id uuid null, metric_name text not null, metric_value numeric(24,6) not null default 0,
 metric_unit text not null default 'number', period_start timestamptz null, period_end timestamptz null,
 metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists idx_ki2_metrics_user on public.koja_intelligence_v2_metrics(user_id, created_at desc);
create index if not exists idx_ki2_metrics_org on public.koja_intelligence_v2_metrics(organization_id, metric_name, created_at desc);

create table if not exists public.koja_intelligence_v2_events (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 organization_id uuid null, event_name text not null, entity_type text null, entity_id text null,
 value numeric(24,6) not null default 0, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists idx_ki2_events_user on public.koja_intelligence_v2_events(user_id, created_at desc);
create index if not exists idx_ki2_events_org on public.koja_intelligence_v2_events(organization_id, event_name, created_at desc);

alter table public.koja_intelligence_v2_metrics enable row level security;
alter table public.koja_intelligence_v2_events enable row level security;
drop policy if exists ki2_metrics_owner on public.koja_intelligence_v2_metrics;
create policy ki2_metrics_owner on public.koja_intelligence_v2_metrics for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists ki2_events_owner on public.koja_intelligence_v2_events;
create policy ki2_events_owner on public.koja_intelligence_v2_events for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
