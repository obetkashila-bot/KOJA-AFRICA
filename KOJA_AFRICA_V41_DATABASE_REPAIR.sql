-- KOJA AFRICA COMPLETE DATABASE / MIGRATION
-- Generated 2026-09-03 for the current Flask application.
-- Run in Supabase SQL Editor. Safe pattern: CREATE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS.
create extension if not exists pgcrypto;


-- Core account/profile
create table if not exists public.profiles (id uuid primary key, full_name text default '', name text, email text unique, phone text, password_hash text, role text default 'student', is_admin boolean default false, is_active boolean default true, institution text, student_number text, vehicle_type text, vehicle_number text, created_at timestamptz default now(), updated_at timestamptz default now());

-- Academic / documents
create table if not exists public.questions (id uuid primary key default gen_random_uuid(), user_id uuid, student_name text, subject text, question text, attachment_name text, attachment_file text, status text default 'Pending', answer_seen boolean default false, created_at timestamptz default now());
create table if not exists public.answers (id uuid primary key default gen_random_uuid(), question_id uuid, answer text, answered_at timestamptz default now(), attachment_name text, attachment_file text);
create table if not exists public.assignments (id uuid primary key default gen_random_uuid(), user_id uuid, student_id uuid, student_name text, email text, student_email text, title text, description text, file_name text, file_path text, file_url text, tracking_code text, status text default 'submitted', answer text, answered_by uuid, answered_at timestamptz, answer_file_name text, answer_file_path text, answer_file_url text, answer_approval_status text default 'pending', approval_status text default 'pending', created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.documents (id uuid primary key default gen_random_uuid(), user_id uuid, title text, description text, file_name text, file_path text, file_url text, category text, is_public boolean default false, is_active boolean default true, approval_status text default 'pending', created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.document_records (id uuid primary key default gen_random_uuid(), document_id uuid, user_id uuid, title text, content text, file_path text, file_url text, created_at timestamptz default now());
create table if not exists public.cv_records (id uuid primary key default gen_random_uuid(), user_id uuid, data jsonb default '{}'::jsonb, file_path text, file_url text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.activity_logs (id uuid primary key default gen_random_uuid(), user_id uuid, action text, description text, created_at timestamptz default now());

-- Professionals
create table if not exists public.service_providers (id uuid primary key default gen_random_uuid(), user_id uuid, full_name text, name text, email text, phone text, profession text, specialty text, bio text, hourly_rate numeric(12,2), consultation_fee numeric(12,2), approval_status text default 'pending', is_active boolean default true, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.doctor_profiles (id uuid primary key default gen_random_uuid(), provider_id uuid, full_name text, specialty text, phone text, location text, bio text, consultation_fee numeric(12,2), approval_status text default 'pending', created_at timestamptz default now());
create table if not exists public.teacher_profiles (id uuid primary key default gen_random_uuid(), provider_id uuid, full_name text, subject text, grade text, phone text, location text, bio text, hourly_rate numeric(12,2), approval_status text default 'pending', created_at timestamptz default now());
create table if not exists public.driver_profiles (id uuid primary key default gen_random_uuid(), provider_id uuid, full_name text, phone text, vehicle_type text, vehicle_registration text, vehicle_number text, license_number text, approval_status text default 'pending', is_active boolean default true, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.driver_locations (id uuid primary key default gen_random_uuid(), driver_id uuid, user_id uuid, latitude double precision, longitude double precision, accuracy double precision, speed double precision, heading double precision, is_online boolean default false, created_at timestamptz default now());
create table if not exists public.appointments (id uuid primary key default gen_random_uuid(), provider_id uuid, user_id uuid, customer_id uuid, appointment_type text, purpose text, booking_date date, booking_time time, notes text, status text default 'pending', approval_status text default 'pending', payment_status text default 'unpaid', created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.professional_reviews (id uuid primary key default gen_random_uuid(), provider_id uuid not null, reviewer_id uuid not null, appointment_id uuid, rating integer check(rating between 1 and 5), review text, created_at timestamptz default now());
create table if not exists public.professional_payments (id uuid primary key default gen_random_uuid(), appointment_id uuid, provider_id uuid, payer_id uuid, amount numeric(12,2) not null default 0, currency text default 'ZMW', status text default 'pending', payment_reference text, transaction_id text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.professional_calls (id uuid primary key default gen_random_uuid(), caller_id uuid, callee_id uuid, mode text default 'video', status text default 'ringing', offer text, answer text, caller_ice jsonb default '[]'::jsonb, callee_ice jsonb default '[]'::jsonb, created_at timestamptz default now(), answered_at timestamptz, ended_at timestamptz);
create table if not exists public.professional_messages (id uuid primary key default gen_random_uuid(), sender_id uuid, receiver_id uuid, message text, message_type text default 'text', file_url text, created_at timestamptz default now());

-- Delivery
create table if not exists public.deliveries (id uuid primary key default gen_random_uuid(), customer_id uuid, driver_id uuid, pickup_address text, delivery_address text, pickup_latitude double precision, pickup_longitude double precision, delivery_latitude double precision, delivery_longitude double precision, status text default 'requested', tracking_code text, accepted_at timestamptz, picked_up_at timestamptz, delivered_at timestamptz, created_at timestamptz default now(), updated_at timestamptz default now(), currency text default 'ZMW', user_id uuid, pickup_location text, destination text, destination_latitude double precision, destination_longitude double precision, recipient_name text, recipient_phone text, package_description text, package_weight numeric, delivery_fee numeric default 0, requested_date date, requested_time time, notes text, approval_status text default 'pending', payment_status text default 'unpaid', payment_reference text);
create table if not exists public.delivery_participant_locations (id uuid primary key default gen_random_uuid(), delivery_id uuid, user_id uuid, latitude double precision, longitude double precision, accuracy double precision, speed double precision, heading double precision, created_at timestamptz default now());
create table if not exists public.koja_delivery_proofs (id uuid primary key default gen_random_uuid(), delivery_id uuid not null, uploaded_by uuid not null, file_url text, file_path text, file_name text, note text, created_at timestamptz default now());
create table if not exists public.owner_locations (id uuid primary key default gen_random_uuid(), user_id uuid, latitude double precision, longitude double precision, accuracy double precision, created_at timestamptz default now());

-- Marketplace extensions
create table if not exists public.koja_blocks (
 blocker_id uuid not null, blocked_id uuid not null, created_at timestamptz default now(), primary key(blocker_id,blocked_id)
);

create table if not exists public.koja_calls (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 caller_id uuid not null, callee_id uuid not null, mode text not null default 'video', status text not null default 'ringing',
 offer text, answer text, caller_ice jsonb default '[]'::jsonb, callee_ice jsonb default '[]'::jsonb,
 created_at timestamptz default now(), answered_at timestamptz, ended_at timestamptz
);

create table if not exists public.koja_contacts (
 id uuid primary key default gen_random_uuid(), requester_id uuid not null, addressee_id uuid not null,
 status text not null default 'pending', created_at timestamptz default now(), updated_at timestamptz default now(),
 unique(requester_id, addressee_id)
);

create table if not exists public.koja_conversation_members (
 conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 user_id uuid not null, role text not null default 'member', joined_at timestamptz default now(), last_read_at timestamptz,
 muted boolean default false, primary key(conversation_id,user_id)
);

create table if not exists public.koja_conversations (
 id uuid primary key default gen_random_uuid(), conversation_type text not null default 'direct', created_by uuid,
 name text, avatar_url text, created_at timestamptz default now(), updated_at timestamptz default now()
);

create table if not exists public.koja_marketplace_orders (
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references public.koja_marketplace_products(id) on delete cascade,
 buyer_id uuid not null,
 seller_id uuid not null,
 amount numeric(12,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 payment_transaction_id text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);

create table if not exists public.koja_marketplace_posts (
 id uuid primary key default gen_random_uuid(),
 author_id uuid not null,
 product_id uuid references public.koja_marketplace_products(id) on delete set null,
 title text,
 body text not null,
 media_url text,
 media_type text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 is_published boolean not null default true
);

create table if not exists public.koja_marketplace_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null,
 category text not null default 'Other',
 price numeric(12,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 cover_url text,
 file_url text,
 file_name text,
 file_size bigint,
 is_published boolean not null default false,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);

create table if not exists public.koja_messages (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 sender_id uuid not null, message_type text not null default 'text', body text default '', file_url text,
 created_at timestamptz default now(), edited_at timestamptz, deleted_at timestamptz
);

create table if not exists public.koja_notifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, notification_type text, title text, body text, related_id uuid,
 is_read boolean default false, created_at timestamptz default now()
);

create table if not exists public.koja_presence (
 user_id uuid primary key, is_online boolean default false, last_seen_at timestamptz default now(), updated_at timestamptz default now()
);

create table if not exists public.koja_public_comments (
 id uuid primary key default gen_random_uuid(),
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 author_id uuid not null, body text not null, created_at timestamptz default now()
);

create table if not exists public.koja_public_likes (
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 user_id uuid not null, created_at timestamptz default now(), primary key(post_id,user_id)
);

create table if not exists public.koja_public_posts (
 id uuid primary key default gen_random_uuid(), author_id uuid not null,
 post_type text not null default 'update', title text, body text not null,
 media_url text, media_type text, created_at timestamptz default now(),
 updated_at timestamptz default now(), is_published boolean default true
);

create table if not exists public.koja_statuses (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, text_content text default '', media_url text,
 media_type text default 'text', visibility text not null default 'contacts',
 expires_at timestamptz not null default (now()+interval '24 hours'), created_at timestamptz default now()
);

CREATE TABLE IF NOT EXISTS public.professional_public_comments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), post_id uuid NOT NULL REFERENCES public.professional_public_posts(id) ON DELETE CASCADE,
 author_id uuid NOT NULL, body text NOT NULL, created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.professional_public_messages (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), profession text NOT NULL,
 sender_id uuid NOT NULL, message text NOT NULL, created_at timestamptz DEFAULT now(), deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS public.professional_public_posts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), profession text NOT NULL, author_id uuid NOT NULL,
 provider_id uuid, title text NOT NULL, body text NOT NULL, media_url text,
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
alter table public.koja_marketplace_products add column if not exists contact_phone text; alter table public.koja_marketplace_products add column if not exists contact_email text; alter table public.koja_marketplace_products add column if not exists whatsapp_number text; alter table public.koja_marketplace_products add column if not exists preferred_contact text default 'KOJA Chat'; alter table public.koja_marketplace_products add column if not exists contact_phone_public boolean default false; alter table public.koja_marketplace_products add column if not exists contact_email_public boolean default false; alter table public.koja_marketplace_products add column if not exists whatsapp_public boolean default false; alter table public.koja_marketplace_products add column if not exists location text; alter table public.koja_marketplace_products add column if not exists town text; alter table public.koja_marketplace_products add column if not exists country text; alter table public.koja_marketplace_products add column if not exists continent text;
create table if not exists public.koja_marketplace_actions (id uuid primary key default gen_random_uuid(), order_id uuid, product_id uuid, actor_id uuid, action text, note text, created_at timestamptz default now());

-- KOJA Connect / communication

create table if not exists public.koja_contacts (id uuid primary key default gen_random_uuid(), requester_id uuid not null, addressee_id uuid not null, status text default 'pending', created_at timestamptz default now(), updated_at timestamptz default now(), unique(requester_id,addressee_id));
create table if not exists public.koja_conversations (id uuid primary key default gen_random_uuid(), conversation_type text default 'direct', created_by uuid, name text, avatar_url text, created_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.koja_conversation_members (conversation_id uuid not null references public.koja_conversations(id) on delete cascade, user_id uuid not null, role text default 'member', joined_at timestamptz default now(), last_read_at timestamptz, muted boolean default false, primary key(conversation_id,user_id));
create table if not exists public.koja_messages (id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade, sender_id uuid not null, message_type text default 'text', body text default '', file_url text, created_at timestamptz default now(), edited_at timestamptz, deleted_at timestamptz);
create table if not exists public.koja_calls (id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade, caller_id uuid not null, callee_id uuid not null, mode text default 'video', status text default 'ringing', offer text, answer text, caller_ice jsonb default '[]'::jsonb, callee_ice jsonb default '[]'::jsonb, created_at timestamptz default now(), answered_at timestamptz, ended_at timestamptz);
create table if not exists public.koja_presence (user_id uuid primary key, is_online boolean default false, last_seen_at timestamptz default now(), updated_at timestamptz default now());
create table if not exists public.koja_statuses (id uuid primary key default gen_random_uuid(), user_id uuid not null, text_content text default '', media_url text, media_type text default 'text', visibility text default 'contacts', expires_at timestamptz default(now()+interval '24 hours'), created_at timestamptz default now());
create table if not exists public.koja_notifications (id uuid primary key default gen_random_uuid(), user_id uuid not null, notification_type text, title text, body text, related_id uuid, is_read boolean default false, created_at timestamptz default now());
create table if not exists public.koja_blocks (blocker_id uuid not null, blocked_id uuid not null, created_at timestamptz default now(), primary key(blocker_id,blocked_id));

-- Public/community and professional community tables from the application
create table if not exists public.professional_public_messages (id uuid primary key default gen_random_uuid(), profession text not null, sender_id uuid not null, message text not null, created_at timestamptz default now(), deleted_at timestamptz); create table if not exists public.professional_public_posts (id uuid primary key default gen_random_uuid(), profession text not null, author_id uuid not null, provider_id uuid, title text not null, body text not null, media_url text, created_at timestamptz default now(), updated_at timestamptz default now()); create table if not exists public.professional_public_comments (id uuid primary key default gen_random_uuid(), post_id uuid not null references public.professional_public_posts(id) on delete cascade, author_id uuid not null, body text not null, created_at timestamptz default now());

-- Indexes used by KOJA
create index if not exists idx_profiles_email on public.profiles(email); create index if not exists idx_questions_user on public.questions(user_id); create index if not exists idx_assignments_user on public.assignments(user_id); create index if not exists idx_assignments_status on public.assignments(status); create index if not exists idx_documents_public on public.documents(is_public,is_active); create index if not exists idx_deliveries_customer on public.deliveries(customer_id,created_at desc); create index if not exists idx_deliveries_driver on public.deliveries(driver_id,created_at desc); create unique index if not exists idx_deliveries_tracking on public.deliveries(tracking_code) where tracking_code is not null; create index if not exists idx_driver_locations_driver on public.driver_locations(driver_id,created_at desc); create index if not exists idx_reviews_provider on public.professional_reviews(provider_id,created_at desc); create index if not exists idx_notifications_user on public.koja_notifications(user_id,is_read,created_at desc); create index if not exists idx_messages_conversation on public.koja_messages(conversation_id,created_at);

-- Compatibility columns for older KOJA databases
alter table public.deliveries add column if not exists pickup_address text; alter table public.deliveries add column if not exists delivery_address text; alter table public.deliveries add column if not exists customer_id uuid; alter table public.deliveries add column if not exists user_id uuid; alter table public.deliveries add column if not exists currency text default 'ZMW';
alter table public.profiles add column if not exists password_hash text; alter table public.profiles add column if not exists is_admin boolean default false; alter table public.profiles add column if not exists is_active boolean default true; alter table public.profiles add column if not exists role text default 'student';

-- End KOJA AFRICA database setup


-- ============================================================
-- KOJA AFRICA V41 FINAL REPAIR / SCHEMA COMPATIBILITY
-- Apply after the base KOJA AFRICA database schema.
-- These additive migrations synchronize the V40/V41 Flask
-- application contracts with the existing Supabase schema.
-- ============================================================

-- Profiles / dedicated administrator identifiers
alter table public.profiles add column if not exists admin_username text;
alter table public.profiles add column if not exists admin_password_hash text;

-- Seed a deterministic username for existing administrators where absent.
update public.profiles
set admin_username = lower(split_part(email, '@', 1))
where coalesce(is_admin,false) = true
  and (admin_username is null or admin_username = '')
  and email is not null;

create unique index if not exists idx_profiles_admin_username
on public.profiles(lower(admin_username))
where admin_username is not null;

-- Professional provider compatibility columns used by V41.
alter table public.service_providers add column if not exists provider_type text default 'professional';
alter table public.service_providers add column if not exists specialization text;
alter table public.service_providers add column if not exists qualification text;
alter table public.service_providers add column if not exists experience_years integer;
alter table public.service_providers add column if not exists service_area text;
alter table public.service_providers add column if not exists address text;
alter table public.service_providers add column if not exists service_description text;
alter table public.service_providers add column if not exists currency text default 'ZMW';
alter table public.service_providers add column if not exists is_available boolean default false;
alter table public.service_providers add column if not exists verification_status text default 'pending';
alter table public.service_providers add column if not exists last_seen_at timestamptz;
alter table public.service_providers add column if not exists updated_at timestamptz default now();

-- Driver compatibility columns used by V41.
alter table public.driver_profiles add column if not exists vehicle_make text;
alter table public.driver_profiles add column if not exists vehicle_model text;
alter table public.driver_profiles add column if not exists driving_license_number text;
alter table public.driver_profiles add column if not exists service_area text;
alter table public.driver_profiles add column if not exists verification_status text default 'pending';

-- Keep legacy/current driver names interoperable.
update public.driver_profiles
set driving_license_number = license_number
where driving_license_number is null and license_number is not null;

update public.driver_profiles
set verification_status = approval_status
where verification_status is null and approval_status is not null;

-- Appointment compatibility columns used by older/current booking handlers.
alter table public.appointments add column if not exists client_id uuid;
alter table public.appointments add column if not exists appointment_date date;
alter table public.appointments add column if not exists start_time time;
alter table public.appointments add column if not exists end_time time;
alter table public.appointments add column if not exists location text;

update public.appointments
set client_id = coalesce(client_id, customer_id, user_id)
where client_id is null;

update public.appointments
set appointment_date = booking_date
where appointment_date is null and booking_date is not null;

update public.appointments
set start_time = booking_time
where start_time is null and booking_time is not null;

-- Professional chat compatibility.
alter table public.professional_messages add column if not exists provider_id uuid;

-- Doctor profile compatibility.
alter table public.doctor_profiles add column if not exists hospital_clinic text;
alter table public.doctor_profiles add column if not exists qualification text;
alter table public.doctor_profiles add column if not exists license_number text;
alter table public.doctor_profiles add column if not exists currency text default 'ZMW';
alter table public.doctor_profiles add column if not exists updated_at timestamptz default now();

-- Teacher profile compatibility.
alter table public.teacher_profiles add column if not exists qualification text;
alter table public.teacher_profiles add column if not exists currency text default 'ZMW';
alter table public.teacher_profiles add column if not exists updated_at timestamptz default now();

-- Documents indexes for search/public approval.
create index if not exists idx_documents_approval_public
on public.documents(approval_status,is_public,is_active,created_at desc);

-- Communication indexes.
create index if not exists idx_professional_messages_provider
on public.professional_messages(provider_id,created_at desc);

-- Appointments indexes.
create index if not exists idx_appointments_client_date
on public.appointments(client_id,appointment_date);

-- Driver verification index.
create index if not exists idx_driver_profiles_approval
on public.driver_profiles(approval_status,verification_status,is_active);

-- End V41 compatibility migration.
