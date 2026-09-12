-- KOJA Documents additive schema hardening
-- Safe for existing data: no table recreation and no destructive operations.

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  title text,
  description text,
  category text default 'Research',
  user_id uuid,
  owner_id uuid,
  file_name text,
  file_path text,
  file_url text,
  file_size bigint,
  mime_type text,
  approval_status text default 'pending',
  status text default 'pending',
  is_public boolean not null default false,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.documents add column if not exists title text;
alter table public.documents add column if not exists description text;
alter table public.documents add column if not exists category text default 'Research';
alter table public.documents add column if not exists user_id uuid;
alter table public.documents add column if not exists owner_id uuid;
alter table public.documents add column if not exists file_name text;
alter table public.documents add column if not exists file_path text;
alter table public.documents add column if not exists file_url text;
alter table public.documents add column if not exists file_size bigint;
alter table public.documents add column if not exists mime_type text;
alter table public.documents add column if not exists approval_status text default 'pending';
alter table public.documents add column if not exists status text default 'pending';
alter table public.documents add column if not exists is_public boolean not null default false;
alter table public.documents add column if not exists is_active boolean not null default true;
alter table public.documents add column if not exists created_at timestamptz not null default now();
alter table public.documents add column if not exists updated_at timestamptz not null default now();

create index if not exists idx_documents_user_id on public.documents(user_id);
create index if not exists idx_documents_approval_status on public.documents(approval_status);
create index if not exists idx_documents_created_at on public.documents(created_at desc);

-- Backfill compatibility values without overwriting existing information.
update public.documents
set owner_id = coalesce(owner_id, user_id)
where owner_id is null and user_id is not null;

update public.documents
set status = coalesce(status, approval_status, 'pending')
where status is null;

update public.documents
set approval_status = coalesce(approval_status, status, 'pending')
where approval_status is null;

-- Verify the columns expected by the KOJA Documents module.
select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'documents'
order by ordinal_position;

-- KOJA Documents AI index (additive, non-destructive)
create table if not exists public.koja_document_ai_index (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null,
  user_id uuid,
  file_name text,
  content text,
  content_characters bigint default 0,
  status text not null default 'ready',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.koja_document_ai_index add column if not exists document_id uuid;
alter table public.koja_document_ai_index add column if not exists user_id uuid;
alter table public.koja_document_ai_index add column if not exists file_name text;
alter table public.koja_document_ai_index add column if not exists content text;
alter table public.koja_document_ai_index add column if not exists content_characters bigint default 0;
alter table public.koja_document_ai_index add column if not exists status text not null default 'ready';
alter table public.koja_document_ai_index add column if not exists created_at timestamptz not null default now();
alter table public.koja_document_ai_index add column if not exists updated_at timestamptz not null default now();

create unique index if not exists uq_koja_document_ai_index_document_id
  on public.koja_document_ai_index(document_id);
create index if not exists idx_koja_document_ai_index_user_id
  on public.koja_document_ai_index(user_id);
create index if not exists idx_koja_document_ai_index_status
  on public.koja_document_ai_index(status);

-- Document learning workspace: additive only
create table if not exists public.koja_document_learning_progress (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null,
  user_id uuid not null,
  action text not null default 'study',
  score numeric,
  total numeric,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.koja_document_learning_progress add column if not exists document_id uuid;
alter table public.koja_document_learning_progress add column if not exists user_id uuid;
alter table public.koja_document_learning_progress add column if not exists action text not null default 'study';
alter table public.koja_document_learning_progress add column if not exists score numeric;
alter table public.koja_document_learning_progress add column if not exists total numeric;
alter table public.koja_document_learning_progress add column if not exists notes text;
alter table public.koja_document_learning_progress add column if not exists created_at timestamptz not null default now();
alter table public.koja_document_learning_progress add column if not exists updated_at timestamptz not null default now();
create index if not exists idx_koja_doc_learning_document_user on public.koja_document_learning_progress(document_id,user_id,created_at desc);

create table if not exists public.koja_document_ai_memory (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null,
  user_id uuid not null,
  memory_type text not null default 'learning',
  content text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.koja_document_ai_memory add column if not exists document_id uuid;
alter table public.koja_document_ai_memory add column if not exists user_id uuid;
alter table public.koja_document_ai_memory add column if not exists memory_type text not null default 'learning';
alter table public.koja_document_ai_memory add column if not exists content text;
alter table public.koja_document_ai_memory add column if not exists created_at timestamptz not null default now();
alter table public.koja_document_ai_memory add column if not exists updated_at timestamptz not null default now();
create index if not exists idx_koja_doc_ai_memory_document_user on public.koja_document_ai_memory(document_id,user_id,created_at desc);
