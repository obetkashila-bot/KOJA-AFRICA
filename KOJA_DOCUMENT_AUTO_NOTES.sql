-- KOJA AFRICA — Automatic AI Document Notes
-- Additive migration. Does not alter or replace the existing documents table.

create table if not exists public.koja_document_auto_notes (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null unique references public.documents(id) on delete cascade,
    note text not null,
    source_updated_at timestamptz,
    generated_at timestamptz not null default now(),
    status text not null default 'ready',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists koja_document_auto_notes_document_idx
    on public.koja_document_auto_notes(document_id);

create index if not exists koja_document_auto_notes_updated_idx
    on public.koja_document_auto_notes(updated_at desc);
