-- KOJA AFRICA FINAL SCHEMA / MIGRATION
-- Run this in Supabase SQL Editor before deploying the final app.
-- It is designed to be safe to re-run.

create extension if not exists pgcrypto;

-- Universal professional directory
create table if not exists public.service_providers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  provider_type text not null default 'professional',
  full_name text,
  name text,
  phone text,
  email text,
  profession text,
  specialization text,
  qualification text,
  experience_years numeric,
  service_area text,
  address text,
  service_description text,
  bio text,
  hourly_rate numeric,
  currency text default 'ZMW',
  approval_status text default 'pending',
  verification_status text default 'pending',
  is_available boolean default false,
  is_active boolean default true,
  profile_image_url text,
  latitude double precision,
  longitude double precision,
  location_label text,
  last_seen_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
alter table public.service_providers add column if not exists provider_type text default 'professional';
alter table public.service_providers add column if not exists full_name text;
alter table public.service_providers add column if not exists name text;
alter table public.service_providers add column if not exists phone text;
alter table public.service_providers add column if not exists email text;
alter table public.service_providers add column if not exists profession text;
alter table public.service_providers add column if not exists specialization text;
alter table public.service_providers add column if not exists qualification text;
alter table public.service_providers add column if not exists experience_years numeric;
alter table public.service_providers add column if not exists service_area text;
alter table public.service_providers add column if not exists address text;
alter table public.service_providers add column if not exists service_description text;
alter table public.service_providers add column if not exists bio text;
alter table public.service_providers add column if not exists hourly_rate numeric;
alter table public.service_providers add column if not exists currency text default 'ZMW';
alter table public.service_providers add column if not exists approval_status text default 'pending';
alter table public.service_providers add column if not exists verification_status text default 'pending';
alter table public.service_providers add column if not exists is_available boolean default false;
alter table public.service_providers add column if not exists is_active boolean default true;
alter table public.service_providers add column if not exists profile_image_url text;
alter table public.service_providers add column if not exists latitude double precision;
alter table public.service_providers add column if not exists longitude double precision;
alter table public.service_providers add column if not exists location_label text;
alter table public.service_providers add column if not exists last_seen_at timestamptz;
alter table public.service_providers add column if not exists created_at timestamptz default now();
alter table public.service_providers add column if not exists updated_at timestamptz default now();
create index if not exists service_providers_public_idx on public.service_providers(provider_type, approval_status, is_active, created_at desc);
create index if not exists service_providers_profession_idx on public.service_providers(profession);

-- Professional private messages
create table if not exists public.professional_messages (
  id uuid primary key default gen_random_uuid(),
  sender_id uuid not null,
  receiver_id uuid not null,
  provider_id uuid not null,
  message text not null,
  created_at timestamptz default now()
);
create index if not exists professional_messages_pair_idx on public.professional_messages(provider_id, created_at);

-- Professional voice/video signaling
create table if not exists public.professional_calls (
  id uuid primary key default gen_random_uuid(),
  caller_id uuid not null,
  callee_id uuid not null,
  provider_id uuid not null,
  mode text not null default 'video',
  status text not null default 'ringing',
  offer text,
  answer text,
  caller_ice jsonb default '[]'::jsonb,
  callee_ice jsonb default '[]'::jsonb,
  created_at timestamptz default now(),
  answered_at timestamptz,
  ended_at timestamptz
);
create index if not exists professional_calls_callee_idx on public.professional_calls(callee_id,status,created_at desc);
create index if not exists professional_calls_caller_idx on public.professional_calls(caller_id,status,created_at desc);

-- Appointments / bookings
create table if not exists public.appointments (
  id uuid primary key default gen_random_uuid(),
  client_id uuid,
  provider_id uuid,
  appointment_type text,
  appointment_date date,
  start_time time,
  end_time time,
  location text,
  status text default 'requested',
  approval_status text default 'pending',
  notes text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
alter table public.appointments add column if not exists client_id uuid;
alter table public.appointments add column if not exists provider_id uuid;
alter table public.appointments add column if not exists appointment_type text;
alter table public.appointments add column if not exists appointment_date date;
alter table public.appointments add column if not exists scheduled_at timestamptz;
alter table public.appointments add column if not exists start_time time;
alter table public.appointments add column if not exists end_time time;
alter table public.appointments add column if not exists location text;
alter table public.appointments add column if not exists status text default 'requested';
alter table public.appointments add column if not exists approval_status text default 'pending';
alter table public.appointments add column if not exists notes text;
alter table public.appointments add column if not exists created_at timestamptz default now();
alter table public.appointments add column if not exists updated_at timestamptz default now();
create index if not exists appointments_provider_idx on public.appointments(provider_id,appointment_date,start_time);

-- Facebook-style public feed
create table if not exists public.koja_public_posts (
 id uuid primary key default gen_random_uuid(),
 author_id uuid not null,
 post_type text not null default 'update',
 title text,
 body text not null,
 media_url text,
 media_type text,
 latitude double precision,
 longitude double precision,
 location_label text,
 created_at timestamptz default now(),
 updated_at timestamptz default now(),
 is_published boolean default true
);
alter table public.koja_public_posts add column if not exists latitude double precision;
alter table public.koja_public_posts add column if not exists longitude double precision;
alter table public.koja_public_posts add column if not exists location_label text;
create index if not exists koja_public_posts_feed_idx on public.koja_public_posts(is_published,created_at desc);
create table if not exists public.koja_public_likes (
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 user_id uuid not null,
 created_at timestamptz default now(),
 primary key(post_id,user_id)
);
create table if not exists public.koja_public_comments (
 id uuid primary key default gen_random_uuid(),
 post_id uuid not null references public.koja_public_posts(id) on delete cascade,
 author_id uuid not null,
 body text not null,
 created_at timestamptz default now()
);
create index if not exists koja_public_comments_post_idx on public.koja_public_comments(post_id,created_at);

-- KOJA Connect: contacts, chats, voice messages, calls and status
create table if not exists public.koja_contacts (
 id uuid primary key default gen_random_uuid(), requester_id uuid not null, addressee_id uuid not null,
 status text not null default 'pending', created_at timestamptz default now(), updated_at timestamptz default now(),
 unique(requester_id,addressee_id)
);
create index if not exists koja_contacts_requester_idx on public.koja_contacts(requester_id,status);
create index if not exists koja_contacts_addressee_idx on public.koja_contacts(addressee_id,status);
create table if not exists public.koja_conversations (
 id uuid primary key default gen_random_uuid(), conversation_type text not null default 'direct', created_by uuid,
 name text, avatar_url text, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_conversation_members (
 conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 user_id uuid not null, role text not null default 'member', joined_at timestamptz default now(), last_read_at timestamptz, muted boolean default false,
 primary key(conversation_id,user_id)
);
create table if not exists public.koja_messages (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 sender_id uuid not null, message_type text not null default 'text', body text default '', file_url text,
 created_at timestamptz default now(), edited_at timestamptz, deleted_at timestamptz
);
create index if not exists koja_messages_conversation_idx on public.koja_messages(conversation_id,created_at);
create table if not exists public.koja_calls (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 caller_id uuid not null, callee_id uuid not null, mode text not null default 'video', status text not null default 'ringing',
 offer text, answer text, caller_ice jsonb default '[]'::jsonb, callee_ice jsonb default '[]'::jsonb,
 created_at timestamptz default now(), answered_at timestamptz, ended_at timestamptz
);
create table if not exists public.koja_presence (
 user_id uuid primary key, is_online boolean default false, last_seen_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_statuses (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, text_content text default '', media_url text,
 media_type text default 'text', visibility text not null default 'contacts', expires_at timestamptz not null default (now()+interval '24 hours'), created_at timestamptz default now()
);
create table if not exists public.koja_notifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, notification_type text, title text, body text, related_id uuid,
 is_read boolean default false, created_at timestamptz default now()
);

-- Marketplace
create table if not exists public.koja_marketplace_products (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null, title text not null, description text not null,
 category text not null default 'Other', price numeric(12,2) not null default 0 check(price>=0), currency text not null default 'ZMW',
 cover_url text, file_url text, file_name text, file_size bigint, is_published boolean not null default false,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_marketplace_products_feed_idx on public.koja_marketplace_products(is_published,created_at desc);
create table if not exists public.koja_marketplace_orders (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_marketplace_products(id) on delete cascade,
 buyer_id uuid not null, seller_id uuid not null, amount numeric(12,2) not null default 0, currency text not null default 'ZMW',
 status text not null default 'pending', payment_method text, payment_reference text, payment_transaction_id text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.koja_marketplace_posts (
 id uuid primary key default gen_random_uuid(), author_id uuid not null,
 product_id uuid references public.koja_marketplace_products(id) on delete set null,
 title text, body text not null, media_url text, media_type text,
 created_at timestamptz default now(), updated_at timestamptz default now(), is_published boolean default true
);
create index if not exists koja_marketplace_posts_feed_idx on public.koja_marketplace_posts(is_published,created_at desc);

-- Professional public-post tables are retained for compatibility, but the final UI uses
-- the main KOJA Public feed for Facebook-style public posts.
create table if not exists public.professional_public_messages (
 id uuid primary key default gen_random_uuid(), profession text not null, sender_id uuid not null,
 message text not null, created_at timestamptz default now(), deleted_at timestamptz
);
create table if not exists public.professional_public_posts (
 id uuid primary key default gen_random_uuid(), profession text not null, author_id uuid not null,
 provider_id uuid, title text not null, body text not null, media_url text,
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.professional_public_comments (
 id uuid primary key default gen_random_uuid(), post_id uuid not null references public.professional_public_posts(id) on delete cascade,
 author_id uuid not null, body text not null, created_at timestamptz default now()
);

-- Useful indexes for approved public professionals
create index if not exists service_providers_location_idx on public.service_providers(latitude,longitude) where latitude is not null and longitude is not null;

-- NOTE: Supabase Storage bucket 'koja-files' should exist. The application uploads media
-- into public-feed/, professional-profiles/, connect/audio/, marketplace/, etc.

-- ============================================================
-- KOJA AFRICA V5 PRODUCTION COMPLETION MIGRATION
-- ============================================================

alter table public.service_providers add column if not exists availability_notes text;
alter table public.service_providers add column if not exists bio text;
alter table public.service_providers add column if not exists updated_at timestamptz default now();
alter table public.profiles add column if not exists email_verified boolean default false;
alter table public.profiles add column if not exists email_verified_at timestamptz;
alter table public.profiles add column if not exists profile_image_url text;

create table if not exists public.professional_reviews (
 id uuid primary key default gen_random_uuid(),
 provider_id uuid not null references public.service_providers(id) on delete cascade,
 user_id uuid not null,
 rating integer not null check (rating between 1 and 5),
 review_text text default '',
 created_at timestamptz default now(),
 updated_at timestamptz default now(),
 unique(provider_id,user_id)
);
create index if not exists professional_reviews_provider_idx on public.professional_reviews(provider_id,created_at desc);

create table if not exists public.koja_reports (
 id uuid primary key default gen_random_uuid(),
 reporter_id uuid not null,
 content_type text not null,
 content_id text not null,
 reason text not null,
 details text default '',
 status text not null default 'pending',
 reviewed_by uuid,
 reviewed_at timestamptz,
 created_at timestamptz default now()
);
create index if not exists koja_reports_status_idx on public.koja_reports(status,created_at desc);

create table if not exists public.koja_account_tokens (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null,
 token_hash text not null,
 token_type text not null,
 expires_at timestamptz not null,
 used boolean default false,
 created_at timestamptz default now(),
 used_at timestamptz
);
create index if not exists koja_account_tokens_lookup_idx on public.koja_account_tokens(user_id,token_type,used,expires_at);

create table if not exists public.koja_live_classes (
 id uuid primary key default gen_random_uuid(),
 provider_id uuid not null,
 booking_id uuid,
 title text not null,
 subject text,
 description text,
 start_at timestamptz not null,
 end_at timestamptz,
 visibility text not null default 'private',
 status text not null default 'scheduled',
 room_token text unique not null,
 attendance_count integer default 0,
 created_at timestamptz default now(),
 updated_at timestamptz default now()
);
create index if not exists koja_live_classes_provider_idx on public.koja_live_classes(provider_id,start_at desc);

create table if not exists public.koja_live_class_members (
 class_id uuid not null references public.koja_live_classes(id) on delete cascade,
 user_id uuid not null,
 role text not null default 'student',
 joined_at timestamptz,
 left_at timestamptz,
 attendance_seconds integer default 0,
 primary key(class_id,user_id)
);

create table if not exists public.koja_product_reviews (
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null,
 user_id uuid not null,
 rating integer not null check(rating between 1 and 5),
 review_text text default '',
 created_at timestamptz default now(),
 updated_at timestamptz default now(),
 unique(product_id,user_id)
);
create index if not exists koja_product_reviews_product_idx on public.koja_product_reviews(product_id,created_at desc);

alter table public.koja_marketplace_products add column if not exists seller_verified boolean default false;
alter table public.koja_marketplace_products add column if not exists moderation_status text default 'pending';
alter table public.koja_marketplace_orders add column if not exists payment_reference text;
alter table public.koja_marketplace_orders add column if not exists updated_at timestamptz default now();

alter table public.appointments add column if not exists updated_at timestamptz default now();
alter table public.appointments add column if not exists cancellation_reason text;
alter table public.appointments add column if not exists meeting_url text;
alter table public.appointments add column if not exists reschedule_requested_at timestamptz;

-- Notification preferences / delivery log.
create table if not exists public.koja_notification_preferences (
 user_id uuid primary key,
 email_enabled boolean default true,
 browser_enabled boolean default true,
 chat_enabled boolean default true,
 booking_enabled boolean default true,
 assignment_enabled boolean default true,
 delivery_enabled boolean default true,
 marketplace_enabled boolean default true,
 updated_at timestamptz default now()
);

-- Helpful moderation indexes.
create index if not exists koja_public_posts_created_idx on public.koja_public_posts(created_at desc);
create index if not exists koja_public_comments_post_idx on public.koja_public_comments(post_id,created_at desc);
create index if not exists koja_marketplace_products_moderation_idx on public.koja_marketplace_products(moderation_status,is_published,created_at desc);


-- KOJA AFRICA V6 completion tables
create table if not exists koja_follows (
 id uuid primary key default gen_random_uuid(), follower_id uuid not null, following_id uuid not null,
 created_at timestamptz default now(), unique(follower_id,following_id)
);
create index if not exists idx_koja_follows_following on koja_follows(following_id);

create table if not exists professional_availability_slots (
 id uuid primary key default gen_random_uuid(), provider_id uuid not null,
 day_of_week int not null check(day_of_week between 0 and 6), start_time time not null, end_time time not null,
 is_active boolean default true, created_at timestamptz default now(), unique(provider_id,day_of_week,start_time,end_time)
);

create table if not exists koja_live_class_members (
 id uuid primary key default gen_random_uuid(), class_id uuid not null, user_id uuid not null,
 role text default 'student', joined_at timestamptz default now(), attendance_status text default 'present', updated_at timestamptz default now(),
 unique(class_id,user_id)
);
create index if not exists idx_live_class_members_class on koja_live_class_members(class_id);

create table if not exists koja_push_subscriptions (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, endpoint text not null,
 p256dh text, auth text, created_at timestamptz default now(), updated_at timestamptz default now(),
 unique(user_id,endpoint)
);

alter table koja_public_posts add column if not exists is_hidden boolean default false;
alter table koja_public_posts add column if not exists moderated_at timestamptz;
alter table koja_public_posts add column if not exists moderated_by uuid;
alter table koja_public_comments add column if not exists is_hidden boolean default false;
alter table koja_public_comments add column if not exists moderated_at timestamptz;
alter table koja_marketplace_products add column if not exists is_hidden boolean default false;
alter table koja_marketplace_products add column if not exists moderated_at timestamptz;
alter table koja_marketplace_posts add column if not exists is_hidden boolean default false;
alter table koja_marketplace_posts add column if not exists moderated_at timestamptz;
alter table koja_reports add column if not exists moderation_action text;
alter table koja_reports add column if not exists reviewed_by uuid;
alter table koja_reports add column if not exists reviewed_at timestamptz;

-- ============================================================
-- KOJA AFRICA V7: real multi-user live classroom signaling
-- and marketplace product reviews
-- ============================================================
create table if not exists public.koja_live_class_signals (
 id uuid primary key default gen_random_uuid(),
 class_id uuid not null references public.koja_live_classes(id) on delete cascade,
 sender_id uuid not null,
 recipient_id uuid not null,
 signal_type text not null,
 payload jsonb,
 created_at timestamptz default now()
);
create index if not exists koja_live_class_signals_recipient_idx
 on public.koja_live_class_signals(class_id,recipient_id,created_at);
create index if not exists koja_live_class_signals_cleanup_idx
 on public.koja_live_class_signals(created_at);

create table if not exists public.koja_marketplace_product_reviews (
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references public.koja_marketplace_products(id) on delete cascade,
 buyer_id uuid not null,
 rating integer not null check(rating between 1 and 5),
 review_text text default '',
 created_at timestamptz default now(),
 updated_at timestamptz default now(),
 unique(product_id,buyer_id)
);
create index if not exists koja_marketplace_product_reviews_product_idx
 on public.koja_marketplace_product_reviews(product_id,created_at desc);

-- ============================================================
-- KOJA AFRICA V8 FINAL INTEGRATION
-- ============================================================
create index if not exists appointments_provider_scheduled_idx on public.appointments(provider_id,scheduled_at);
create index if not exists appointments_client_scheduled_idx on public.appointments(client_id,scheduled_at);
create index if not exists koja_push_subscriptions_user_idx on public.koja_push_subscriptions(user_id);
alter table public.koja_live_class_members add column if not exists control_request text;
alter table public.koja_live_classes add column if not exists ended_at timestamptz;
alter table public.koja_marketplace_orders add column if not exists payment_status text default 'unpaid';
alter table public.koja_marketplace_orders add column if not exists paid_at timestamptz;
alter table public.koja_marketplace_orders add column if not exists updated_at timestamptz default now();

-- ============================================================
-- KOJA V8 TEACHER DIRECTORY + ACTIVITY LOG COMPATIBILITY
-- ============================================================
create table if not exists public.teacher_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  provider_id uuid,
  full_name text,
  teacher_name text,
  email text,
  phone text,
  subjects text,
  grade_levels text,
  qualification text,
  experience_years numeric,
  hourly_rate numeric,
  currency text default 'ZMW',
  service_area text,
  bio text,
  approval_status text default 'pending',
  is_active boolean default true,
  approved_by uuid,
  approved_at timestamptz,
  approval_note text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
alter table public.teacher_profiles add column if not exists user_id uuid;
alter table public.teacher_profiles add column if not exists provider_id uuid;
alter table public.teacher_profiles add column if not exists full_name text;
alter table public.teacher_profiles add column if not exists teacher_name text;
alter table public.teacher_profiles add column if not exists email text;
alter table public.teacher_profiles add column if not exists phone text;
alter table public.teacher_profiles add column if not exists subjects text;
alter table public.teacher_profiles add column if not exists grade_levels text;
alter table public.teacher_profiles add column if not exists qualification text;
alter table public.teacher_profiles add column if not exists experience_years numeric;
alter table public.teacher_profiles add column if not exists hourly_rate numeric;
alter table public.teacher_profiles add column if not exists currency text default 'ZMW';
alter table public.teacher_profiles add column if not exists service_area text;
alter table public.teacher_profiles add column if not exists bio text;
alter table public.teacher_profiles add column if not exists approval_status text default 'pending';
alter table public.teacher_profiles add column if not exists is_active boolean default true;
alter table public.teacher_profiles add column if not exists approved_by uuid;
alter table public.teacher_profiles add column if not exists approved_at timestamptz;
alter table public.teacher_profiles add column if not exists approval_note text;
alter table public.teacher_profiles add column if not exists created_at timestamptz default now();
alter table public.teacher_profiles add column if not exists updated_at timestamptz default now();
create index if not exists teacher_profiles_public_idx on public.teacher_profiles(approval_status,is_active,created_at desc);
create index if not exists teacher_profiles_user_idx on public.teacher_profiles(user_id);

-- Existing deployments may have activity_logs.user_id incorrectly referencing a legacy users table.
alter table if exists public.activity_logs drop constraint if exists activity_logs_user_id_fkey;
alter table if exists public.activity_logs add constraint activity_logs_user_id_fkey
  foreign key (user_id) references public.profiles(id) on delete set null not valid;

