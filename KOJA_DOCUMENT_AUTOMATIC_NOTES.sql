-- KOJA AFRICA — Automatic Document Notes reliability migration
-- Additive/idempotent. Existing KOJA Document AI is unchanged.
-- Run once in the existing KOJA AFRICA Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.koja_document_automatic_notes (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null,
  file_name text default '',
  content_hash text default '',
  source_characters bigint not null default 0,
  note_text text default '',
  status text not null default 'queued',
  error_message text default '',
  attempts integer not null default 0,
  started_at timestamptz,
  lease_until timestamptz,
  generated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.koja_document_automatic_notes add column if not exists document_id uuid;
alter table public.koja_document_automatic_notes add column if not exists file_name text default '';
alter table public.koja_document_automatic_notes add column if not exists content_hash text default '';
alter table public.koja_document_automatic_notes add column if not exists source_characters bigint not null default 0;
alter table public.koja_document_automatic_notes add column if not exists note_text text default '';
alter table public.koja_document_automatic_notes add column if not exists status text not null default 'queued';
alter table public.koja_document_automatic_notes add column if not exists error_message text default '';
alter table public.koja_document_automatic_notes add column if not exists attempts integer not null default 0;
alter table public.koja_document_automatic_notes add column if not exists started_at timestamptz;
alter table public.koja_document_automatic_notes add column if not exists lease_until timestamptz;
alter table public.koja_document_automatic_notes add column if not exists generated_at timestamptz;
alter table public.koja_document_automatic_notes add column if not exists created_at timestamptz not null default now();
alter table public.koja_document_automatic_notes add column if not exists updated_at timestamptz not null default now();

create unique index if not exists koja_document_automatic_notes_document_uidx
  on public.koja_document_automatic_notes(document_id);
create index if not exists koja_document_automatic_notes_status_idx
  on public.koja_document_automatic_notes(status, updated_at desc);
create index if not exists koja_document_automatic_notes_hash_idx
  on public.koja_document_automatic_notes(document_id, content_hash);
create index if not exists koja_document_automatic_notes_lease_idx
  on public.koja_document_automatic_notes(status, lease_until);

-- Recover rows from the earlier implementation that could remain forever in
-- "generating" because they had no durable lease. They will be re-queued by
-- the application and processed by the background worker.
update public.koja_document_automatic_notes
set status = 'queued',
    lease_until = null,
    error_message = '',
    updated_at = now()
where lower(coalesce(status, '')) = 'generating'
  and (lease_until is null or lease_until < now());

-- Existing error rows are retryable. The application will retry them when the
-- document workspace is opened, while successful notes remain untouched.
update public.koja_document_automatic_notes
set status = 'queued',
    error_message = '',
    updated_at = now()
where lower(coalesce(status, '')) in ('error','failed');
