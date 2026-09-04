-- KOJA AFRICA Teacher Profit Centre
-- Run this in Supabase SQL Editor before using paid classes, packages or availability.
create table if not exists public.teacher_classes (
 id uuid primary key default gen_random_uuid(), teacher_id uuid not null, provider_id uuid,
 title text not null, subject text, description text, class_type text not null default 'online',
 class_date date, start_time time, end_time time, capacity integer default 1,
 price numeric default 0, currency text default 'ZMW', meeting_url text, location text,
 status text default 'published', created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists teacher_classes_teacher_idx on public.teacher_classes(teacher_id, class_date, start_time);
create index if not exists teacher_classes_status_idx on public.teacher_classes(status, class_date, start_time);
create table if not exists public.teacher_packages (
 id uuid primary key default gen_random_uuid(), teacher_id uuid not null, provider_id uuid,
 name text not null, subject text, lessons integer default 4, validity_days integer default 30,
 price numeric default 0, currency text default 'ZMW', description text, status text default 'published',
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists teacher_packages_teacher_idx on public.teacher_packages(teacher_id, status);
create table if not exists public.teacher_availability (
 id uuid primary key default gen_random_uuid(), teacher_id uuid not null, day_of_week integer not null,
 start_time time not null, end_time time not null, mode text default 'online', is_active boolean default true,
 created_at timestamptz default now()
);
create index if not exists teacher_availability_teacher_idx on public.teacher_availability(teacher_id, day_of_week);
