-- KOJA AFRICA: Registered-user assignment answering + paid answer unlocks
-- Run in Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.koja_assignment_answers (
    id uuid primary key default gen_random_uuid(),
    assignment_id uuid not null unique,
    answerer_id uuid not null,
    answer_text text,
    answer_file_name text,
    answer_file_path text,
    status text not null default 'submitted',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists koja_assignment_answers_answerer_idx
    on public.koja_assignment_answers(answerer_id, created_at desc);
create index if not exists koja_assignment_answers_created_idx
    on public.koja_assignment_answers(created_at desc);

create table if not exists public.koja_assignment_answer_orders (
    id uuid primary key default gen_random_uuid(),
    assignment_id uuid not null,
    answer_id uuid not null,
    buyer_id uuid not null,
    amount numeric(12,2) not null default 10,
    currency text not null default 'ZMW',
    status text not null default 'pending',
    payment_method text,
    payment_reference text unique,
    payment_transaction_id text,
    created_at timestamptz not null default now(),
    paid_at timestamptz,
    updated_at timestamptz not null default now()
);

create index if not exists koja_assignment_answer_orders_buyer_idx
    on public.koja_assignment_answer_orders(buyer_id, created_at desc);
create index if not exists koja_assignment_answer_orders_assignment_idx
    on public.koja_assignment_answer_orders(assignment_id, status, created_at desc);
create unique index if not exists koja_assignment_answer_orders_paid_once_idx
    on public.koja_assignment_answer_orders(assignment_id, buyer_id)
    where status = 'paid';

-- Compatibility columns for installations that already created a community-answer table.
alter table public.koja_assignment_answers add column if not exists answer_file_name text;
alter table public.koja_assignment_answers add column if not exists answer_file_path text;
alter table public.koja_assignment_answers add column if not exists status text default 'submitted';
alter table public.koja_assignment_answers add column if not exists updated_at timestamptz default now();
