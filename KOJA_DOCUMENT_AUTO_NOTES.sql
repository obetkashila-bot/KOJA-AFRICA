-- KOJA AFRICA: additive automatic document notes migration
-- Run once in Supabase SQL Editor.
-- Does not alter or replace the existing KOJA Document AI tables.

create table if not exists public.koja_document_auto_notes (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null unique references public.documents(id) on delete cascade,
    user_id uuid,
    version_hash text not null default '',
    note text not null default '',
    status text not null default 'pending',
    error_message text,
    source_characters integer not null default 0,
    source_file_name text,
    generated_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_koja_document_auto_notes_user
    on public.koja_document_auto_notes(user_id);

create index if not exists idx_koja_document_auto_notes_status
    on public.koja_document_auto_notes(status);

create index if not exists idx_koja_document_auto_notes_updated
    on public.koja_document_auto_notes(updated_at desc);

-- Keep the note owner synchronized when the document owner is known.
create or replace function public.koja_sync_document_auto_note_owner()
returns trigger
language plpgsql
as $$
begin
    update public.koja_document_auto_notes
       set user_id = new.user_id,
           updated_at = now()
     where document_id = new.id;
    return new;
end;
$$;

drop trigger if exists trg_koja_sync_document_auto_note_owner
on public.documents;

create trigger trg_koja_sync_document_auto_note_owner
after update of user_id on public.documents
for each row
execute function public.koja_sync_document_auto_note_owner();

-- Helpful RLS baseline. The Flask server uses the Supabase REST service role
-- for database operations, so these policies do not replace server-side access checks.
alter table public.koja_document_auto_notes enable row level security;

drop policy if exists "koja_document_auto_notes_owner_read"
on public.koja_document_auto_notes;

create policy "koja_document_auto_notes_owner_read"
on public.koja_document_auto_notes
for select
using (
    auth.uid() = user_id
    or exists (
        select 1
        from public.documents d
        where d.id = document_id
          and (
              d.is_public = true
              or d.approval_status in ('approved','published','public','active')
          )
    )
);

-- No browser INSERT/UPDATE policy is intentionally granted.
-- Automatic notes are written by KOJA AFRICA's server-side application.
