-- KOJA AFRICA — Automatic Document Notes
-- Additive/idempotent migration. Does not replace existing Document AI tables.
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
alter table public.koja_document_automatic_notes add column if not exists generated_at timestamptz;
alter table public.koja_document_automatic_notes add column if not exists created_at timestamptz not null default now();
alter table public.koja_document_automatic_notes add column if not exists updated_at timestamptz not null default now();

create unique index if not exists koja_document_automatic_notes_document_uidx
  on public.koja_document_automatic_notes(document_id);
create index if not exists koja_document_automatic_notes_status_idx
  on public.koja_document_automatic_notes(status, updated_at desc);
create index if not exists koja_document_automatic_notes_hash_idx
  on public.koja_document_automatic_notes(document_id, content_hash);

-- Existing rows are intentionally left queued. KOJA AFRICA generates their
-- notes lazily/in the background when the Documents workspace is opened.
