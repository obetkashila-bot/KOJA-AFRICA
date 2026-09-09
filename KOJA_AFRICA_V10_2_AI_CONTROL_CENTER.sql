-- KOJA AFRICA V10.2 AI CONTROL CENTER
-- Safe/idempotent migration. Does not recreate existing tables.

create table if not exists public.koja_ai_provider_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  provider text not null,
  model text default '',
  event_type text not null,
  latency_ms integer default 0,
  error_code text default '',
  created_at timestamptz not null default now()
);
create index if not exists koja_ai_provider_events_created_idx on public.koja_ai_provider_events(created_at desc);
create index if not exists koja_ai_provider_events_provider_idx on public.koja_ai_provider_events(provider,created_at desc);

alter table if exists public.koja_ai_usage add column if not exists provider text default '';
alter table if exists public.koja_ai_usage add column if not exists model text default '';

