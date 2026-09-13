-- ============================================================
-- KOJA AFRICA MASTER SQL 2026-09-12
-- Consolidated additive/idempotent deployment SQL
-- Run in Supabase SQL Editor. Review duplicate legacy sections before production.
-- ============================================================


-- ============================================================
-- SOURCE: KOJA_AFRICA_DATABASE(3).sql
-- ============================================================
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
-- SOURCE: KOJA_AFRICA_V7_COMPLETE.sql
-- ============================================================
create table if not exists public.koja_ai_conversations (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 title text not null default 'New KOJA AI chat', is_archived boolean not null default false,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_ai_conversations_user_idx on public.koja_ai_conversations(user_id, updated_at desc);
create table if not exists public.koja_ai_messages (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_ai_conversations(id) on delete cascade,
 user_id uuid not null, role text not null check (role in ('user','assistant')), content text not null,
 created_at timestamptz not null default now()
);
create index if not exists koja_ai_messages_conversation_idx on public.koja_ai_messages(conversation_id, created_at asc);
create index if not exists koja_ai_messages_user_idx on public.koja_ai_messages(user_id, created_at desc);
notify pgrst, 'reload schema';
create table if not exists public.koja_news_reactions (post_id uuid not null references public.koja_public_posts(id) on delete cascade,user_id uuid not null,reaction text not null default 'like',created_at timestamptz default now(),primary key(post_id,user_id));
create index if not exists koja_news_reactions_post_idx on public.koja_news_reactions(post_id);
create table if not exists public.koja_media_events (id uuid primary key default gen_random_uuid(),post_id uuid references public.koja_public_posts(id) on delete cascade,user_id uuid,session_id text not null,event_type text not null,watch_seconds numeric default 0,completion_percent numeric default 0,created_at timestamptz default now());
create index if not exists koja_media_events_post_idx on public.koja_media_events(post_id,created_at desc);
create index if not exists koja_media_events_session_idx on public.koja_media_events(session_id,created_at desc);
create table if not exists public.koja_ai_feedback (id uuid primary key default gen_random_uuid(),user_id uuid,rating text,prompt_hash text,created_at timestamptz default now());
create table if not exists public.koja_market_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null default '',
 category text not null default 'Other',
 product_type text not null default 'physical',
 price numeric(14,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 stock integer not null default 1 check (stock >= 0),
 sku text,
 image_url text,
 digital_file_url text,
 digital_file_name text,
 delivery_available boolean not null default true,
 delivery_fee numeric(14,2) not null default 0 check (delivery_fee >= 0),
 location text,
 is_published boolean not null default false,
 approval_status text not null default 'pending',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_products_feed_idx on public.koja_market_products(is_published,approval_status,created_at desc);
create index if not exists koja_market_products_seller_idx on public.koja_market_products(seller_id,created_at desc);
create index if not exists koja_market_products_category_idx on public.koja_market_products(category,created_at desc);

create table if not exists public.koja_market_orders (
 id uuid primary key default gen_random_uuid(),
 order_number text unique not null,
 product_id uuid not null references public.koja_market_products(id) on delete restrict,
 buyer_id uuid not null,
 seller_id uuid not null,
 quantity integer not null default 1 check (quantity > 0),
 item_amount numeric(14,2) not null default 0,
 delivery_fee numeric(14,2) not null default 0,
 total_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0,
 seller_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 payment_transaction_id text,
 recipient_name text,
 recipient_phone text,
 delivery_address text,
 notes text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_orders_buyer_idx on public.koja_market_orders(buyer_id,created_at desc);
create index if not exists koja_market_orders_seller_idx on public.koja_market_orders(seller_id,created_at desc);
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);

create table if not exists public.koja_market_sellers (
 id uuid primary key default gen_random_uuid(),
 user_id uuid unique not null,
 store_name text not null,
 description text default '',
 phone text,
 location text,
 approval_status text not null default 'pending',
 is_active boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_sellers_status_idx on public.koja_market_sellers(approval_status,is_active);

-- Safe compatibility additions when the tables already exist.
alter table public.koja_market_products add column if not exists product_type text default 'physical';
alter table public.koja_market_products add column if not exists stock integer default 1;
alter table public.koja_market_products add column if not exists sku text;
alter table public.koja_market_products add column if not exists image_url text;
alter table public.koja_market_products add column if not exists digital_file_url text;
alter table public.koja_market_products add column if not exists digital_file_name text;
alter table public.koja_market_products add column if not exists delivery_available boolean default true;
alter table public.koja_market_products add column if not exists delivery_fee numeric(14,2) default 0;
alter table public.koja_market_products add column if not exists location text;
alter table public.koja_market_products add column if not exists approval_status text default 'pending';

create table if not exists public.koja_market_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null default '',
 category text not null default 'Other',
 product_type text not null default 'physical',
 price numeric(14,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 stock integer not null default 1 check (stock >= 0),
 sku text,
 image_url text,
 digital_file_url text,
 digital_file_name text,
 delivery_available boolean not null default true,
 delivery_fee numeric(14,2) not null default 0 check (delivery_fee >= 0),
 location text,
 is_published boolean not null default false,
 approval_status text not null default 'pending',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_products_feed_idx on public.koja_market_products(is_published,approval_status,created_at desc);
create index if not exists koja_market_products_seller_idx on public.koja_market_products(seller_id,created_at desc);
create index if not exists koja_market_products_category_idx on public.koja_market_products(category,created_at desc);

create table if not exists public.koja_market_orders (
 id uuid primary key default gen_random_uuid(),
 order_number text unique not null,
 product_id uuid not null references public.koja_market_products(id) on delete restrict,
 buyer_id uuid not null,
 seller_id uuid not null,
 quantity integer not null default 1 check (quantity > 0),
 item_amount numeric(14,2) not null default 0,
 delivery_fee numeric(14,2) not null default 0,
 total_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0,
 seller_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 payment_transaction_id text,
 recipient_name text,
 recipient_phone text,
 delivery_address text,
 notes text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_orders_buyer_idx on public.koja_market_orders(buyer_id,created_at desc);
create index if not exists koja_market_orders_seller_idx on public.koja_market_orders(seller_id,created_at desc);
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);

create table if not exists public.koja_market_sellers (
 id uuid primary key default gen_random_uuid(),
 user_id uuid unique not null,
 store_name text not null,
 description text default '',
 phone text,
 location text,
 approval_status text not null default 'pending',
 is_active boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_sellers_status_idx on public.koja_market_sellers(approval_status,is_active);

-- Safe compatibility additions when the tables already exist.
alter table public.koja_market_products add column if not exists product_type text default 'physical';
alter table public.koja_market_products add column if not exists stock integer default 1;
alter table public.koja_market_products add column if not exists sku text;
alter table public.koja_market_products add column if not exists image_url text;
alter table public.koja_market_products add column if not exists digital_file_url text;
alter table public.koja_market_products add column if not exists digital_file_name text;
alter table public.koja_market_products add column if not exists delivery_available boolean default true;
alter table public.koja_market_products add column if not exists delivery_fee numeric(14,2) default 0;
alter table public.koja_market_products add column if not exists location text;
alter table public.koja_market_products add column if not exists approval_status text default 'pending';
create table if not exists public.koja_market_cart (id uuid primary key default gen_random_uuid(), user_id uuid not null, product_id uuid not null references public.koja_market_products(id) on delete cascade, quantity integer not null default 1 check(quantity>0), created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(user_id,product_id));
create table if not exists public.koja_market_wishlist (id uuid primary key default gen_random_uuid(), user_id uuid not null, product_id uuid not null references public.koja_market_products(id) on delete cascade, created_at timestamptz not null default now(), unique(user_id,product_id));
-- KOJA MARKET V3 + KOJA BUSINESS commercial engine
-- Run after KOJA_MARKET.sql / KOJA_MARKET_V2.sql. All statements are idempotent.

alter table public.koja_market_orders add column if not exists platform_fee numeric(14,2) not null default 0;
alter table public.koja_market_orders add column if not exists payout_status text not null default 'pending';
alter table public.koja_market_orders add column if not exists delivery_status text not null default 'not_requested';

create table if not exists public.koja_market_seller_subscriptions (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null references public.koja_market_sellers(id) on delete cascade,
 user_id uuid not null, plan text not null default 'free', monthly_price numeric(14,2) not null default 0,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(seller_id)
);
create index if not exists koja_market_seller_subs_user_idx on public.koja_market_seller_subscriptions(user_id,status);

create table if not exists public.koja_market_featured (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 seller_id uuid not null, days integer not null default 7, price numeric(14,2) not null default 0,
 status text not null default 'pending', starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now()
);
create index if not exists koja_market_featured_active_idx on public.koja_market_featured(status,ends_at);

create table if not exists public.koja_market_ads (
 id uuid primary key default gen_random_uuid(), advertiser_id uuid not null, title text not null,
 target_url text, placement text not null default 'market', budget numeric(14,2) not null default 0,
 spent numeric(14,2) not null default 0, status text not null default 'pending', impressions bigint not null default 0,
 clicks bigint not null default 0, starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_ads_status_idx on public.koja_market_ads(status,placement);

create table if not exists public.koja_market_reviews (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 buyer_id uuid not null, rating integer not null check(rating between 1 and 5), review text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(product_id,buyer_id)
);

create table if not exists public.koja_market_ledger (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 seller_id uuid not null, buyer_id uuid, gross_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0, platform_fee numeric(14,2) not null default 0,
 net_amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 status text not null default 'pending', created_at timestamptz not null default now()
);
create index if not exists koja_market_ledger_seller_idx on public.koja_market_ledger(seller_id,created_at desc);

create table if not exists public.koja_market_payment_fees (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 buyer_id uuid, amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 fee_type text not null default 'platform_service_fee', provider text, reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_market_delivery_jobs (
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.koja_market_orders(id) on delete cascade,
 customer_id uuid, driver_id uuid, pickup_address text, delivery_address text, delivery_fee numeric(14,2) not null default 0,
 status text not null default 'requested', tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_delivery_jobs_status_idx on public.koja_market_delivery_jobs(status,created_at desc);

-- Business SaaS
create table if not exists public.koja_businesses (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null,
 category text not null default 'General', phone text, location text, logo_url text,
 currency text not null default 'ZMW', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_businesses_owner_idx on public.koja_businesses(owner_id,created_at desc);

create table if not exists public.koja_business_subscriptions (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 owner_id uuid not null, plan text not null default 'starter', monthly_price numeric(14,2) not null default 99,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_products (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, sku text, selling_price numeric(14,2) not null default 0, cost_price numeric(14,2) not null default 0,
 stock integer not null default 0, reorder_level integer not null default 0, active boolean not null default true,
 market_product_id uuid references public.koja_market_products(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_products_biz_idx on public.koja_business_products(business_id,created_at desc);

create table if not exists public.koja_business_stock_movements (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 product_id uuid not null references public.koja_business_products(id) on delete cascade, movement_type text not null,
 quantity integer not null, reference text, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_sales (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 customer_id uuid, product_id uuid, invoice_id uuid, quantity integer not null default 1,
 total_amount numeric(14,2) not null default 0, payment_method text, status text not null default 'paid', description text default '', created_at timestamptz not null default now()
);
create index if not exists koja_business_sales_biz_idx on public.koja_business_sales(business_id,created_at desc);

create table if not exists public.koja_business_expenses (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 supplier_id uuid, category text, amount numeric(14,2) not null default 0, description text default '', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_customers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_customers_biz_idx on public.koja_business_customers(business_id,name);

create table if not exists public.koja_business_suppliers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_invoices (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 invoice_number text not null, customer_id uuid, subtotal numeric(14,2) not null default 0,
 tax_amount numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0,
 status text not null default 'draft', due_date date, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id,invoice_number)
);

create table if not exists public.koja_business_invoice_items (
 id uuid primary key default gen_random_uuid(), invoice_id uuid not null references public.koja_business_invoices(id) on delete cascade,
 product_id uuid, description text not null, quantity numeric(14,2) not null default 1, unit_price numeric(14,2) not null default 0, total numeric(14,2) not null default 0
);

create table if not exists public.koja_business_employees (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, role text, salary numeric(14,2) not null default 0,
 pay_frequency text not null default 'monthly', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_payroll (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 employee_id uuid not null references public.koja_business_employees(id) on delete cascade, period_start date not null,
 period_end date not null, gross_pay numeric(14,2) not null default 0, deductions numeric(14,2) not null default 0,
 net_pay numeric(14,2) not null default 0, status text not null default 'pending', paid_at timestamptz, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_stores (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 slug text unique not null, store_name text not null, description text default '', published boolean not null default false,
 market_enabled boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_ai_usage (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 user_id uuid, prompt text, response_summary text, tokens integer not null default 0, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_payments (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 amount numeric(14,2) not null default 0, currency text not null default 'ZMW', method text, provider text,
 reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_delivery (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 order_reference text, customer_id uuid, address text, fee numeric(14,2) not null default 0,
 status text not null default 'requested', driver_id uuid, tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_ai_plans (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 plan text not null default 'included', monthly_limit integer not null default 100, used_count integer not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);
-- KOJA MARKET V3 + KOJA BUSINESS commercial engine
-- Run after KOJA_MARKET.sql / KOJA_MARKET_V2.sql. All statements are idempotent.

alter table public.koja_market_orders add column if not exists platform_fee numeric(14,2) not null default 0;
alter table public.koja_market_orders add column if not exists payout_status text not null default 'pending';
alter table public.koja_market_orders add column if not exists delivery_status text not null default 'not_requested';

create table if not exists public.koja_market_seller_subscriptions (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null references public.koja_market_sellers(id) on delete cascade,
 user_id uuid not null, plan text not null default 'free', monthly_price numeric(14,2) not null default 0,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(seller_id)
);
create index if not exists koja_market_seller_subs_user_idx on public.koja_market_seller_subscriptions(user_id,status);

create table if not exists public.koja_market_featured (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 seller_id uuid not null, days integer not null default 7, price numeric(14,2) not null default 0,
 status text not null default 'pending', starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now()
);
create index if not exists koja_market_featured_active_idx on public.koja_market_featured(status,ends_at);

create table if not exists public.koja_market_ads (
 id uuid primary key default gen_random_uuid(), advertiser_id uuid not null, title text not null,
 target_url text, placement text not null default 'market', budget numeric(14,2) not null default 0,
 spent numeric(14,2) not null default 0, status text not null default 'pending', impressions bigint not null default 0,
 clicks bigint not null default 0, starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_ads_status_idx on public.koja_market_ads(status,placement);

create table if not exists public.koja_market_reviews (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 buyer_id uuid not null, rating integer not null check(rating between 1 and 5), review text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(product_id,buyer_id)
);

create table if not exists public.koja_market_ledger (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 seller_id uuid not null, buyer_id uuid, gross_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0, platform_fee numeric(14,2) not null default 0,
 net_amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 status text not null default 'pending', created_at timestamptz not null default now()
);
create index if not exists koja_market_ledger_seller_idx on public.koja_market_ledger(seller_id,created_at desc);

create table if not exists public.koja_market_payment_fees (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 buyer_id uuid, amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 fee_type text not null default 'platform_service_fee', provider text, reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_market_delivery_jobs (
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.koja_market_orders(id) on delete cascade,
 customer_id uuid, driver_id uuid, pickup_address text, delivery_address text, delivery_fee numeric(14,2) not null default 0,
 status text not null default 'requested', tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_delivery_jobs_status_idx on public.koja_market_delivery_jobs(status,created_at desc);

-- Business SaaS
create table if not exists public.koja_businesses (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null,
 category text not null default 'General', phone text, location text, logo_url text,
 currency text not null default 'ZMW', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_businesses_owner_idx on public.koja_businesses(owner_id,created_at desc);

create table if not exists public.koja_business_subscriptions (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 owner_id uuid not null, plan text not null default 'starter', monthly_price numeric(14,2) not null default 99,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_products (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, sku text, selling_price numeric(14,2) not null default 0, cost_price numeric(14,2) not null default 0,
 stock integer not null default 0, reorder_level integer not null default 0, active boolean not null default true,
 market_product_id uuid references public.koja_market_products(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_products_biz_idx on public.koja_business_products(business_id,created_at desc);

create table if not exists public.koja_business_stock_movements (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 product_id uuid not null references public.koja_business_products(id) on delete cascade, movement_type text not null,
 quantity integer not null, reference text, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_sales (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 customer_id uuid, product_id uuid, invoice_id uuid, quantity integer not null default 1,
 total_amount numeric(14,2) not null default 0, payment_method text, status text not null default 'paid', description text default '', created_at timestamptz not null default now()
);
create index if not exists koja_business_sales_biz_idx on public.koja_business_sales(business_id,created_at desc);

create table if not exists public.koja_business_expenses (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 supplier_id uuid, category text, amount numeric(14,2) not null default 0, description text default '', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_customers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_customers_biz_idx on public.koja_business_customers(business_id,name);

create table if not exists public.koja_business_suppliers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_invoices (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 invoice_number text not null, customer_id uuid, subtotal numeric(14,2) not null default 0,
 tax_amount numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0,
 status text not null default 'draft', due_date date, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id,invoice_number)
);

create table if not exists public.koja_business_invoice_items (
 id uuid primary key default gen_random_uuid(), invoice_id uuid not null references public.koja_business_invoices(id) on delete cascade,
 product_id uuid, description text not null, quantity numeric(14,2) not null default 1, unit_price numeric(14,2) not null default 0, total numeric(14,2) not null default 0
);

create table if not exists public.koja_business_employees (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, role text, salary numeric(14,2) not null default 0,
 pay_frequency text not null default 'monthly', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_payroll (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 employee_id uuid not null references public.koja_business_employees(id) on delete cascade, period_start date not null,
 period_end date not null, gross_pay numeric(14,2) not null default 0, deductions numeric(14,2) not null default 0,
 net_pay numeric(14,2) not null default 0, status text not null default 'pending', paid_at timestamptz, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_stores (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 slug text unique not null, store_name text not null, description text default '', published boolean not null default false,
 market_enabled boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_ai_usage (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 user_id uuid, prompt text, response_summary text, tokens integer not null default 0, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_payments (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 amount numeric(14,2) not null default 0, currency text not null default 'ZMW', method text, provider text,
 reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_delivery (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 order_reference text, customer_id uuid, address text, fee numeric(14,2) not null default 0,
 status text not null default 'requested', driver_id uuid, tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_ai_plans (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 plan text not null default 'included', monthly_limit integer not null default 100, used_count integer not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);


-- V4 production commerce additions
create table if not exists public.koja_market_payouts (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null, user_id uuid not null,
 amount numeric(14,2) not null check(amount>0), currency text not null default 'ZMW', method text not null default 'mobile_money',
 destination text not null, status text not null default 'requested', provider_reference text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_payouts_seller_idx on public.koja_market_payouts(seller_id,status,created_at desc);

create table if not exists public.koja_market_coupons (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null, code text not null,
 discount_percent numeric(6,2) not null check(discount_percent>0 and discount_percent<=100),
 usage_limit integer not null default 0, used_count integer not null default 0, active boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(seller_id,code)
);
create index if not exists koja_market_coupons_code_idx on public.koja_market_coupons(code,active);

alter table public.koja_business_products add column if not exists low_stock_alert boolean not null default true;
alter table public.koja_business_products add column if not exists barcode text;
alter table public.koja_business_subscriptions add column if not exists provider text;
alter table public.koja_business_subscriptions add column if not exists payment_reference text;
alter table public.koja_market_ads add column if not exists billing_status text not null default 'unbilled';
alter table public.koja_market_featured add column if not exists billing_status text not null default 'unbilled';

-- Optional reconciliation/reporting indexes
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);
create index if not exists koja_market_payment_fees_status_idx on public.koja_market_payment_fees(status,created_at desc);
create index if not exists koja_business_payments_status_idx on public.koja_business_payments(status,created_at desc);
create index if not exists koja_business_delivery_status_idx on public.koja_business_delivery(status,created_at desc);

-- ============================================================
-- KOJA AFRICA V7 COMPLETE MONETIZATION / GROWTH
-- Clean consolidated migration. Safe to run more than once.
-- ============================================================

create table if not exists public.koja_monetization_orders (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, order_type text not null,
 target_id uuid, plan text, title text, target_url text, placement text default 'market', days integer,
 amount numeric(14,2) not null default 0, currency text not null default 'ZMW', status text not null default 'pending',
 payment_reference text unique, payment_transaction_id text, paid_at timestamptz,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_mono_orders_user_idx on public.koja_monetization_orders(user_id,created_at desc);
create index if not exists koja_mono_orders_status_idx on public.koja_monetization_orders(status,created_at desc);

create table if not exists public.koja_monetization_ledger (
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.koja_monetization_orders(id) on delete cascade,
 user_id uuid not null, order_type text not null, gross_amount numeric(14,2) not null default 0,
 platform_revenue numeric(14,2) not null default 0, seller_payout numeric(14,2) not null default 0,
 currency text not null default 'ZMW', status text not null default 'posted', created_at timestamptz not null default now()
);
create index if not exists koja_mono_ledger_date_idx on public.koja_monetization_ledger(created_at desc);

create table if not exists public.koja_monetization_events (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, event_type text not null,
 target_id uuid, amount numeric(14,2) not null default 0, created_at timestamptz not null default now()
);

create table if not exists public.koja_payout_requests (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, amount numeric(14,2) not null,
 currency text not null default 'ZMW', phone text not null, status text not null default 'pending',
 admin_note text default '', processed_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_payout_user_idx on public.koja_payout_requests(user_id,status,created_at desc);

create table if not exists public.koja_seller_verifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null unique, legal_name text not null,
 phone text default '', document_type text not null, document_number text not null,
 status text not null default 'pending', admin_note text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_seller_verifications_status_idx on public.koja_seller_verifications(status,created_at desc);

create table if not exists public.koja_referrals (
 id uuid primary key default gen_random_uuid(), referrer_id uuid not null, referred_user_id uuid,
 code text not null, reward_amount numeric(14,2) not null default 0, status text not null default 'active',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_referrals_referrer_idx on public.koja_referrals(referrer_id,created_at desc);
create index if not exists koja_referrals_code_idx on public.koja_referrals(code);

create table if not exists public.koja_ai_subscriptions (
 id uuid primary key default gen_random_uuid(), user_id uuid not null unique, plan text not null default 'free',
 monthly_price numeric(14,2) not null default 0, status text not null default 'active',
 started_at timestamptz default now(), expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_ai_usage (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, usage_date date not null default current_date,
 requests integer not null default 0, input_tokens bigint not null default 0, output_tokens bigint not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(user_id,usage_date)
);
create index if not exists koja_ai_usage_user_date_idx on public.koja_ai_usage(user_id,usage_date desc);

create table if not exists public.koja_security_events (
 id uuid primary key default gen_random_uuid(), user_id uuid, event_type text not null, ip_address text default '',
 user_agent text default '', details jsonb default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists koja_security_events_date_idx on public.koja_security_events(created_at desc);

-- Helpful compatibility columns used by the V7 application where absent.
alter table if exists public.profiles add column if not exists is_admin boolean default false;
alter table if exists public.profiles add column if not exists is_active boolean default true;
alter table if exists public.profiles add column if not exists role text default 'user';
alter table if exists public.deliveries add column if not exists currency text default 'ZMW';
alter table if exists public.deliveries add column if not exists user_id uuid;

-- ============================================================
-- End KOJA AFRICA V7 COMPLETE migration
-- ============================================================


-- ============================================================
-- SOURCE: KOJA_AFRICA_V8_COMPLETE(3).sql
-- ============================================================
create table if not exists public.koja_ai_conversations (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 title text not null default 'New KOJA AI chat', is_archived boolean not null default false,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_ai_conversations_user_idx on public.koja_ai_conversations(user_id, updated_at desc);
create table if not exists public.koja_ai_messages (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_ai_conversations(id) on delete cascade,
 user_id uuid not null, role text not null check (role in ('user','assistant')), content text not null,
 created_at timestamptz not null default now()
);
create index if not exists koja_ai_messages_conversation_idx on public.koja_ai_messages(conversation_id, created_at asc);
create index if not exists koja_ai_messages_user_idx on public.koja_ai_messages(user_id, created_at desc);
notify pgrst, 'reload schema';
create table if not exists public.koja_news_reactions (post_id uuid not null references public.koja_public_posts(id) on delete cascade,user_id uuid not null,reaction text not null default 'like',created_at timestamptz default now(),primary key(post_id,user_id));
create index if not exists koja_news_reactions_post_idx on public.koja_news_reactions(post_id);
create table if not exists public.koja_media_events (id uuid primary key default gen_random_uuid(),post_id uuid references public.koja_public_posts(id) on delete cascade,user_id uuid,session_id text not null,event_type text not null,watch_seconds numeric default 0,completion_percent numeric default 0,created_at timestamptz default now());
create index if not exists koja_media_events_post_idx on public.koja_media_events(post_id,created_at desc);
create index if not exists koja_media_events_session_idx on public.koja_media_events(session_id,created_at desc);
create table if not exists public.koja_ai_feedback (id uuid primary key default gen_random_uuid(),user_id uuid,rating text,prompt_hash text,created_at timestamptz default now());
create table if not exists public.koja_market_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null default '',
 category text not null default 'Other',
 product_type text not null default 'physical',
 price numeric(14,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 stock integer not null default 1 check (stock >= 0),
 sku text,
 image_url text,
 digital_file_url text,
 digital_file_name text,
 delivery_available boolean not null default true,
 delivery_fee numeric(14,2) not null default 0 check (delivery_fee >= 0),
 location text,
 is_published boolean not null default false,
 approval_status text not null default 'pending',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_products_feed_idx on public.koja_market_products(is_published,approval_status,created_at desc);
create index if not exists koja_market_products_seller_idx on public.koja_market_products(seller_id,created_at desc);
create index if not exists koja_market_products_category_idx on public.koja_market_products(category,created_at desc);

create table if not exists public.koja_market_orders (
 id uuid primary key default gen_random_uuid(),
 order_number text unique not null,
 product_id uuid not null references public.koja_market_products(id) on delete restrict,
 buyer_id uuid not null,
 seller_id uuid not null,
 quantity integer not null default 1 check (quantity > 0),
 item_amount numeric(14,2) not null default 0,
 delivery_fee numeric(14,2) not null default 0,
 total_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0,
 seller_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 payment_transaction_id text,
 recipient_name text,
 recipient_phone text,
 delivery_address text,
 notes text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_orders_buyer_idx on public.koja_market_orders(buyer_id,created_at desc);
create index if not exists koja_market_orders_seller_idx on public.koja_market_orders(seller_id,created_at desc);
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);

create table if not exists public.koja_market_sellers (
 id uuid primary key default gen_random_uuid(),
 user_id uuid unique not null,
 store_name text not null,
 description text default '',
 phone text,
 location text,
 approval_status text not null default 'pending',
 is_active boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_sellers_status_idx on public.koja_market_sellers(approval_status,is_active);

-- Safe compatibility additions when the tables already exist.
alter table public.koja_market_products add column if not exists product_type text default 'physical';
alter table public.koja_market_products add column if not exists stock integer default 1;
alter table public.koja_market_products add column if not exists sku text;
alter table public.koja_market_products add column if not exists image_url text;
alter table public.koja_market_products add column if not exists digital_file_url text;
alter table public.koja_market_products add column if not exists digital_file_name text;
alter table public.koja_market_products add column if not exists delivery_available boolean default true;
alter table public.koja_market_products add column if not exists delivery_fee numeric(14,2) default 0;
alter table public.koja_market_products add column if not exists location text;
alter table public.koja_market_products add column if not exists approval_status text default 'pending';

create table if not exists public.koja_market_products (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 title text not null,
 description text not null default '',
 category text not null default 'Other',
 product_type text not null default 'physical',
 price numeric(14,2) not null default 0 check (price >= 0),
 currency text not null default 'ZMW',
 stock integer not null default 1 check (stock >= 0),
 sku text,
 image_url text,
 digital_file_url text,
 digital_file_name text,
 delivery_available boolean not null default true,
 delivery_fee numeric(14,2) not null default 0 check (delivery_fee >= 0),
 location text,
 is_published boolean not null default false,
 approval_status text not null default 'pending',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_products_feed_idx on public.koja_market_products(is_published,approval_status,created_at desc);
create index if not exists koja_market_products_seller_idx on public.koja_market_products(seller_id,created_at desc);
create index if not exists koja_market_products_category_idx on public.koja_market_products(category,created_at desc);

create table if not exists public.koja_market_orders (
 id uuid primary key default gen_random_uuid(),
 order_number text unique not null,
 product_id uuid not null references public.koja_market_products(id) on delete restrict,
 buyer_id uuid not null,
 seller_id uuid not null,
 quantity integer not null default 1 check (quantity > 0),
 item_amount numeric(14,2) not null default 0,
 delivery_fee numeric(14,2) not null default 0,
 total_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0,
 seller_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 payment_method text,
 payment_reference text,
 payment_transaction_id text,
 recipient_name text,
 recipient_phone text,
 delivery_address text,
 notes text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_orders_buyer_idx on public.koja_market_orders(buyer_id,created_at desc);
create index if not exists koja_market_orders_seller_idx on public.koja_market_orders(seller_id,created_at desc);
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);

create table if not exists public.koja_market_sellers (
 id uuid primary key default gen_random_uuid(),
 user_id uuid unique not null,
 store_name text not null,
 description text default '',
 phone text,
 location text,
 approval_status text not null default 'pending',
 is_active boolean not null default true,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_sellers_status_idx on public.koja_market_sellers(approval_status,is_active);

-- Safe compatibility additions when the tables already exist.
alter table public.koja_market_products add column if not exists product_type text default 'physical';
alter table public.koja_market_products add column if not exists stock integer default 1;
alter table public.koja_market_products add column if not exists sku text;
alter table public.koja_market_products add column if not exists image_url text;
alter table public.koja_market_products add column if not exists digital_file_url text;
alter table public.koja_market_products add column if not exists digital_file_name text;
alter table public.koja_market_products add column if not exists delivery_available boolean default true;
alter table public.koja_market_products add column if not exists delivery_fee numeric(14,2) default 0;
alter table public.koja_market_products add column if not exists location text;
alter table public.koja_market_products add column if not exists approval_status text default 'pending';
create table if not exists public.koja_market_cart (id uuid primary key default gen_random_uuid(), user_id uuid not null, product_id uuid not null references public.koja_market_products(id) on delete cascade, quantity integer not null default 1 check(quantity>0), created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(user_id,product_id));
create table if not exists public.koja_market_wishlist (id uuid primary key default gen_random_uuid(), user_id uuid not null, product_id uuid not null references public.koja_market_products(id) on delete cascade, created_at timestamptz not null default now(), unique(user_id,product_id));
-- KOJA MARKET V3 + KOJA BUSINESS commercial engine
-- Run after KOJA_MARKET.sql / KOJA_MARKET_V2.sql. All statements are idempotent.

alter table public.koja_market_orders add column if not exists platform_fee numeric(14,2) not null default 0;
alter table public.koja_market_orders add column if not exists payout_status text not null default 'pending';
alter table public.koja_market_orders add column if not exists delivery_status text not null default 'not_requested';

create table if not exists public.koja_market_seller_subscriptions (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null references public.koja_market_sellers(id) on delete cascade,
 user_id uuid not null, plan text not null default 'free', monthly_price numeric(14,2) not null default 0,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(seller_id)
);
create index if not exists koja_market_seller_subs_user_idx on public.koja_market_seller_subscriptions(user_id,status);

create table if not exists public.koja_market_featured (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 seller_id uuid not null, days integer not null default 7, price numeric(14,2) not null default 0,
 status text not null default 'pending', starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now()
);
create index if not exists koja_market_featured_active_idx on public.koja_market_featured(status,ends_at);

create table if not exists public.koja_market_ads (
 id uuid primary key default gen_random_uuid(), advertiser_id uuid not null, title text not null,
 target_url text, placement text not null default 'market', budget numeric(14,2) not null default 0,
 spent numeric(14,2) not null default 0, status text not null default 'pending', impressions bigint not null default 0,
 clicks bigint not null default 0, starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_ads_status_idx on public.koja_market_ads(status,placement);

create table if not exists public.koja_market_reviews (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 buyer_id uuid not null, rating integer not null check(rating between 1 and 5), review text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(product_id,buyer_id)
);

create table if not exists public.koja_market_ledger (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 seller_id uuid not null, buyer_id uuid, gross_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0, platform_fee numeric(14,2) not null default 0,
 net_amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 status text not null default 'pending', created_at timestamptz not null default now()
);
create index if not exists koja_market_ledger_seller_idx on public.koja_market_ledger(seller_id,created_at desc);

create table if not exists public.koja_market_payment_fees (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 buyer_id uuid, amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 fee_type text not null default 'platform_service_fee', provider text, reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_market_delivery_jobs (
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.koja_market_orders(id) on delete cascade,
 customer_id uuid, driver_id uuid, pickup_address text, delivery_address text, delivery_fee numeric(14,2) not null default 0,
 status text not null default 'requested', tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_delivery_jobs_status_idx on public.koja_market_delivery_jobs(status,created_at desc);

-- Business SaaS
create table if not exists public.koja_businesses (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null,
 category text not null default 'General', phone text, location text, logo_url text,
 currency text not null default 'ZMW', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_businesses_owner_idx on public.koja_businesses(owner_id,created_at desc);

create table if not exists public.koja_business_subscriptions (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 owner_id uuid not null, plan text not null default 'starter', monthly_price numeric(14,2) not null default 99,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_products (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, sku text, selling_price numeric(14,2) not null default 0, cost_price numeric(14,2) not null default 0,
 stock integer not null default 0, reorder_level integer not null default 0, active boolean not null default true,
 market_product_id uuid references public.koja_market_products(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_products_biz_idx on public.koja_business_products(business_id,created_at desc);

create table if not exists public.koja_business_stock_movements (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 product_id uuid not null references public.koja_business_products(id) on delete cascade, movement_type text not null,
 quantity integer not null, reference text, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_sales (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 customer_id uuid, product_id uuid, invoice_id uuid, quantity integer not null default 1,
 total_amount numeric(14,2) not null default 0, payment_method text, status text not null default 'paid', description text default '', created_at timestamptz not null default now()
);
create index if not exists koja_business_sales_biz_idx on public.koja_business_sales(business_id,created_at desc);

create table if not exists public.koja_business_expenses (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 supplier_id uuid, category text, amount numeric(14,2) not null default 0, description text default '', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_customers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_customers_biz_idx on public.koja_business_customers(business_id,name);

create table if not exists public.koja_business_suppliers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_invoices (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 invoice_number text not null, customer_id uuid, subtotal numeric(14,2) not null default 0,
 tax_amount numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0,
 status text not null default 'draft', due_date date, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id,invoice_number)
);

create table if not exists public.koja_business_invoice_items (
 id uuid primary key default gen_random_uuid(), invoice_id uuid not null references public.koja_business_invoices(id) on delete cascade,
 product_id uuid, description text not null, quantity numeric(14,2) not null default 1, unit_price numeric(14,2) not null default 0, total numeric(14,2) not null default 0
);

create table if not exists public.koja_business_employees (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, role text, salary numeric(14,2) not null default 0,
 pay_frequency text not null default 'monthly', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_payroll (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 employee_id uuid not null references public.koja_business_employees(id) on delete cascade, period_start date not null,
 period_end date not null, gross_pay numeric(14,2) not null default 0, deductions numeric(14,2) not null default 0,
 net_pay numeric(14,2) not null default 0, status text not null default 'pending', paid_at timestamptz, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_stores (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 slug text unique not null, store_name text not null, description text default '', published boolean not null default false,
 market_enabled boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_ai_usage (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 user_id uuid, prompt text, response_summary text, tokens integer not null default 0, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_payments (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 amount numeric(14,2) not null default 0, currency text not null default 'ZMW', method text, provider text,
 reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_delivery (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 order_reference text, customer_id uuid, address text, fee numeric(14,2) not null default 0,
 status text not null default 'requested', driver_id uuid, tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_ai_plans (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 plan text not null default 'included', monthly_limit integer not null default 100, used_count integer not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);
-- KOJA MARKET V3 + KOJA BUSINESS commercial engine
-- Run after KOJA_MARKET.sql / KOJA_MARKET_V2.sql. All statements are idempotent.

alter table public.koja_market_orders add column if not exists platform_fee numeric(14,2) not null default 0;
alter table public.koja_market_orders add column if not exists payout_status text not null default 'pending';
alter table public.koja_market_orders add column if not exists delivery_status text not null default 'not_requested';

create table if not exists public.koja_market_seller_subscriptions (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null references public.koja_market_sellers(id) on delete cascade,
 user_id uuid not null, plan text not null default 'free', monthly_price numeric(14,2) not null default 0,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(seller_id)
);
create index if not exists koja_market_seller_subs_user_idx on public.koja_market_seller_subscriptions(user_id,status);

create table if not exists public.koja_market_featured (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 seller_id uuid not null, days integer not null default 7, price numeric(14,2) not null default 0,
 status text not null default 'pending', starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now()
);
create index if not exists koja_market_featured_active_idx on public.koja_market_featured(status,ends_at);

create table if not exists public.koja_market_ads (
 id uuid primary key default gen_random_uuid(), advertiser_id uuid not null, title text not null,
 target_url text, placement text not null default 'market', budget numeric(14,2) not null default 0,
 spent numeric(14,2) not null default 0, status text not null default 'pending', impressions bigint not null default 0,
 clicks bigint not null default 0, starts_at timestamptz, ends_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_ads_status_idx on public.koja_market_ads(status,placement);

create table if not exists public.koja_market_reviews (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.koja_market_products(id) on delete cascade,
 buyer_id uuid not null, rating integer not null check(rating between 1 and 5), review text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(product_id,buyer_id)
);

create table if not exists public.koja_market_ledger (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 seller_id uuid not null, buyer_id uuid, gross_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0, platform_fee numeric(14,2) not null default 0,
 net_amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 status text not null default 'pending', created_at timestamptz not null default now()
);
create index if not exists koja_market_ledger_seller_idx on public.koja_market_ledger(seller_id,created_at desc);

create table if not exists public.koja_market_payment_fees (
 id uuid primary key default gen_random_uuid(), order_id uuid references public.koja_market_orders(id) on delete set null,
 buyer_id uuid, amount numeric(14,2) not null default 0, currency text not null default 'ZMW',
 fee_type text not null default 'platform_service_fee', provider text, reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_market_delivery_jobs (
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.koja_market_orders(id) on delete cascade,
 customer_id uuid, driver_id uuid, pickup_address text, delivery_address text, delivery_fee numeric(14,2) not null default 0,
 status text not null default 'requested', tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_delivery_jobs_status_idx on public.koja_market_delivery_jobs(status,created_at desc);

-- Business SaaS
create table if not exists public.koja_businesses (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null, name text not null,
 category text not null default 'General', phone text, location text, logo_url text,
 currency text not null default 'ZMW', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_businesses_owner_idx on public.koja_businesses(owner_id,created_at desc);

create table if not exists public.koja_business_subscriptions (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 owner_id uuid not null, plan text not null default 'starter', monthly_price numeric(14,2) not null default 99,
 status text not null default 'pending', started_at timestamptz, expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_products (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, sku text, selling_price numeric(14,2) not null default 0, cost_price numeric(14,2) not null default 0,
 stock integer not null default 0, reorder_level integer not null default 0, active boolean not null default true,
 market_product_id uuid references public.koja_market_products(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_products_biz_idx on public.koja_business_products(business_id,created_at desc);

create table if not exists public.koja_business_stock_movements (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 product_id uuid not null references public.koja_business_products(id) on delete cascade, movement_type text not null,
 quantity integer not null, reference text, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_sales (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 customer_id uuid, product_id uuid, invoice_id uuid, quantity integer not null default 1,
 total_amount numeric(14,2) not null default 0, payment_method text, status text not null default 'paid', description text default '', created_at timestamptz not null default now()
);
create index if not exists koja_business_sales_biz_idx on public.koja_business_sales(business_id,created_at desc);

create table if not exists public.koja_business_expenses (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 supplier_id uuid, category text, amount numeric(14,2) not null default 0, description text default '', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_customers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_business_customers_biz_idx on public.koja_business_customers(business_id,name);

create table if not exists public.koja_business_suppliers (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, address text, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_invoices (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 invoice_number text not null, customer_id uuid, subtotal numeric(14,2) not null default 0,
 tax_amount numeric(14,2) not null default 0, total_amount numeric(14,2) not null default 0,
 status text not null default 'draft', due_date date, notes text, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id,invoice_number)
);

create table if not exists public.koja_business_invoice_items (
 id uuid primary key default gen_random_uuid(), invoice_id uuid not null references public.koja_business_invoices(id) on delete cascade,
 product_id uuid, description text not null, quantity numeric(14,2) not null default 1, unit_price numeric(14,2) not null default 0, total numeric(14,2) not null default 0
);

create table if not exists public.koja_business_employees (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 name text not null, phone text, email text, role text, salary numeric(14,2) not null default 0,
 pay_frequency text not null default 'monthly', status text not null default 'active', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_payroll (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 employee_id uuid not null references public.koja_business_employees(id) on delete cascade, period_start date not null,
 period_end date not null, gross_pay numeric(14,2) not null default 0, deductions numeric(14,2) not null default 0,
 net_pay numeric(14,2) not null default 0, status text not null default 'pending', paid_at timestamptz, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_stores (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 slug text unique not null, store_name text not null, description text default '', published boolean not null default false,
 market_enabled boolean not null default true, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);

create table if not exists public.koja_business_ai_usage (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 user_id uuid, prompt text, response_summary text, tokens integer not null default 0, created_at timestamptz not null default now()
);

create table if not exists public.koja_business_payments (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 amount numeric(14,2) not null default 0, currency text not null default 'ZMW', method text, provider text,
 reference text, status text not null default 'pending', created_at timestamptz not null default now()
);

create table if not exists public.koja_business_delivery (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 order_reference text, customer_id uuid, address text, fee numeric(14,2) not null default 0,
 status text not null default 'requested', driver_id uuid, tracking_code text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_business_ai_plans (
 id uuid primary key default gen_random_uuid(), business_id uuid not null references public.koja_businesses(id) on delete cascade,
 plan text not null default 'included', monthly_limit integer not null default 100, used_count integer not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(business_id)
);


-- V4 production commerce additions
create table if not exists public.koja_market_payouts (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null, user_id uuid not null,
 amount numeric(14,2) not null check(amount>0), currency text not null default 'ZMW', method text not null default 'mobile_money',
 destination text not null, status text not null default 'requested', provider_reference text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_market_payouts_seller_idx on public.koja_market_payouts(seller_id,status,created_at desc);

create table if not exists public.koja_market_coupons (
 id uuid primary key default gen_random_uuid(), seller_id uuid not null, code text not null,
 discount_percent numeric(6,2) not null check(discount_percent>0 and discount_percent<=100),
 usage_limit integer not null default 0, used_count integer not null default 0, active boolean not null default true,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(seller_id,code)
);
create index if not exists koja_market_coupons_code_idx on public.koja_market_coupons(code,active);

alter table public.koja_business_products add column if not exists low_stock_alert boolean not null default true;
alter table public.koja_business_products add column if not exists barcode text;
alter table public.koja_business_subscriptions add column if not exists provider text;
alter table public.koja_business_subscriptions add column if not exists payment_reference text;
alter table public.koja_market_ads add column if not exists billing_status text not null default 'unbilled';
alter table public.koja_market_featured add column if not exists billing_status text not null default 'unbilled';

-- Optional reconciliation/reporting indexes
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);
create index if not exists koja_market_payment_fees_status_idx on public.koja_market_payment_fees(status,created_at desc);
create index if not exists koja_business_payments_status_idx on public.koja_business_payments(status,created_at desc);
create index if not exists koja_business_delivery_status_idx on public.koja_business_delivery(status,created_at desc);

-- ============================================================
-- KOJA AFRICA V7 COMPLETE MONETIZATION / GROWTH
-- Clean consolidated migration. Safe to run more than once.
-- ============================================================

create table if not exists public.koja_monetization_orders (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, order_type text not null,
 target_id uuid, plan text, title text, target_url text, placement text default 'market', days integer,
 amount numeric(14,2) not null default 0, currency text not null default 'ZMW', status text not null default 'pending',
 payment_reference text unique, payment_transaction_id text, paid_at timestamptz,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_mono_orders_user_idx on public.koja_monetization_orders(user_id,created_at desc);
create index if not exists koja_mono_orders_status_idx on public.koja_monetization_orders(status,created_at desc);

create table if not exists public.koja_monetization_ledger (
 id uuid primary key default gen_random_uuid(), order_id uuid not null references public.koja_monetization_orders(id) on delete cascade,
 user_id uuid not null, order_type text not null, gross_amount numeric(14,2) not null default 0,
 platform_revenue numeric(14,2) not null default 0, seller_payout numeric(14,2) not null default 0,
 currency text not null default 'ZMW', status text not null default 'posted', created_at timestamptz not null default now()
);
create index if not exists koja_mono_ledger_date_idx on public.koja_monetization_ledger(created_at desc);

create table if not exists public.koja_monetization_events (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, event_type text not null,
 target_id uuid, amount numeric(14,2) not null default 0, created_at timestamptz not null default now()
);

create table if not exists public.koja_payout_requests (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, amount numeric(14,2) not null,
 currency text not null default 'ZMW', phone text not null, status text not null default 'pending',
 admin_note text default '', processed_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_payout_user_idx on public.koja_payout_requests(user_id,status,created_at desc);

create table if not exists public.koja_seller_verifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null unique, legal_name text not null,
 phone text default '', document_type text not null, document_number text not null,
 status text not null default 'pending', admin_note text default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_seller_verifications_status_idx on public.koja_seller_verifications(status,created_at desc);

create table if not exists public.koja_referrals (
 id uuid primary key default gen_random_uuid(), referrer_id uuid not null, referred_user_id uuid,
 code text not null, reward_amount numeric(14,2) not null default 0, status text not null default 'active',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_referrals_referrer_idx on public.koja_referrals(referrer_id,created_at desc);
create index if not exists koja_referrals_code_idx on public.koja_referrals(code);

create table if not exists public.koja_ai_subscriptions (
 id uuid primary key default gen_random_uuid(), user_id uuid not null unique, plan text not null default 'free',
 monthly_price numeric(14,2) not null default 0, status text not null default 'active',
 started_at timestamptz default now(), expires_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.koja_ai_usage (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, usage_date date not null default current_date,
 requests integer not null default 0, input_tokens bigint not null default 0, output_tokens bigint not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(user_id,usage_date)
);
create index if not exists koja_ai_usage_user_date_idx on public.koja_ai_usage(user_id,usage_date desc);

create table if not exists public.koja_security_events (
 id uuid primary key default gen_random_uuid(), user_id uuid, event_type text not null, ip_address text default '',
 user_agent text default '', details jsonb default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists koja_security_events_date_idx on public.koja_security_events(created_at desc);

-- Helpful compatibility columns used by the V7 application where absent.
alter table if exists public.profiles add column if not exists is_admin boolean default false;
alter table if exists public.profiles add column if not exists is_active boolean default true;
alter table if exists public.profiles add column if not exists role text default 'user';
alter table if exists public.deliveries add column if not exists currency text default 'ZMW';
alter table if exists public.deliveries add column if not exists user_id uuid;

-- ============================================================
-- End KOJA AFRICA V7 COMPLETE migration
-- ============================================================


-- ============================================================
-- V8 BUSINESS / POS MODULE
-- ============================================================
-- KOJA AFRICA V8 — BUSINESS / POS MODULE
-- Revenue engine: business subscriptions + POS + inventory + sales + expenses

create table if not exists public.koja_businesses (
 id uuid primary key default gen_random_uuid(),
 owner_id uuid not null unique,
 business_name text not null,
 category text not null default 'General',
 phone text,
 location text,
 plan text not null default 'free',
 plan_status text not null default 'active',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_businesses_category_idx on public.koja_businesses(category);

create table if not exists public.koja_business_products (
 id uuid primary key default gen_random_uuid(),
 business_id uuid not null references public.koja_businesses(id) on delete cascade,
 title text not null,
 sku text,
 category text not null default 'General',
 price numeric(14,2) not null default 0 check(price>=0),
 cost_price numeric(14,2) not null default 0 check(cost_price>=0),
 stock integer not null default 0 check(stock>=0),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_business_products_business_idx on public.koja_business_products(business_id,created_at desc);

create table if not exists public.koja_business_sales (
 id uuid primary key default gen_random_uuid(),
 business_id uuid not null references public.koja_businesses(id) on delete cascade,
 customer_name text,
 payment_method text not null default 'cash',
 total_amount numeric(14,2) not null default 0 check(total_amount>=0),
 profit_amount numeric(14,2) not null default 0,
 status text not null default 'completed',
 created_at timestamptz not null default now()
);
create index if not exists koja_business_sales_business_idx on public.koja_business_sales(business_id,created_at desc);

create table if not exists public.koja_business_sale_items (
 id uuid primary key default gen_random_uuid(),
 sale_id uuid not null references public.koja_business_sales(id) on delete cascade,
 product_id uuid not null references public.koja_business_products(id) on delete restrict,
 quantity integer not null check(quantity>0),
 unit_price numeric(14,2) not null default 0,
 cost_price numeric(14,2) not null default 0,
 line_total numeric(14,2) not null default 0,
 created_at timestamptz not null default now()
);
create index if not exists koja_business_sale_items_sale_idx on public.koja_business_sale_items(sale_id);

create table if not exists public.koja_business_expenses (
 id uuid primary key default gen_random_uuid(),
 business_id uuid not null references public.koja_businesses(id) on delete cascade,
 title text not null,
 category text not null default 'General',
 amount numeric(14,2) not null check(amount>0),
 created_at timestamptz not null default now()
);
create index if not exists koja_business_expenses_business_idx on public.koja_business_expenses(business_id,created_at desc);

alter table public.koja_businesses add column if not exists plan text default 'free';
alter table public.koja_businesses add column if not exists plan_status text default 'active';


-- ============================================================
-- SOURCE: KOJA_V8_MARKET_COMPLETE.sql
-- ============================================================
-- KOJA V8 MARKET COMPLETE
-- Safe/idempotent migration for the existing physical + digital Marketplace.
-- Does not delete/recreate existing Market data or touch Communications.

create extension if not exists pgcrypto;

-- Existing Market tables: compatibility columns.
alter table if exists public.koja_market_products add column if not exists product_type text default 'physical';
alter table if exists public.koja_market_products add column if not exists stock integer default 1;
alter table if exists public.koja_market_products add column if not exists sku text;
alter table if exists public.koja_market_products add column if not exists image_url text;
alter table if exists public.koja_market_products add column if not exists digital_file_url text;
alter table if exists public.koja_market_products add column if not exists digital_file_name text;
alter table if exists public.koja_market_products add column if not exists delivery_available boolean default true;
alter table if exists public.koja_market_products add column if not exists delivery_fee numeric(14,2) default 0;
alter table if exists public.koja_market_products add column if not exists location text;
alter table if exists public.koja_market_products add column if not exists approval_status text default 'pending';
alter table if exists public.koja_market_products add column if not exists is_published boolean default false;

alter table if exists public.koja_market_sellers add column if not exists verification_status text default 'pending';
alter table if exists public.koja_market_sellers add column if not exists verification_id_url text;
alter table if exists public.koja_market_sellers add column if not exists verification_business_url text;
alter table if exists public.koja_market_sellers add column if not exists updated_at timestamptz not null default now();

-- Seller subscriptions and advertising/featured listings.
create table if not exists public.koja_market_seller_subscriptions (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null references public.koja_market_sellers(id) on delete cascade,
 user_id uuid not null,
 plan text not null default 'free',
 monthly_price numeric(14,2) not null default 0,
 status text not null default 'pending',
 payment_reference text,
 provider text,
 started_at timestamptz,
 expires_at timestamptz,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(seller_id)
);
create index if not exists koja_market_seller_subs_user_idx on public.koja_market_seller_subscriptions(user_id,status);

create table if not exists public.koja_market_featured (
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references public.koja_market_products(id) on delete cascade,
 seller_id uuid not null,
 days integer not null default 7,
 price numeric(14,2) not null default 0,
 status text not null default 'pending',
 starts_at timestamptz,
 ends_at timestamptz,
 created_at timestamptz not null default now()
);
create index if not exists koja_market_featured_active_idx on public.koja_market_featured(status,ends_at);

create table if not exists public.koja_market_ads (
 id uuid primary key default gen_random_uuid(),
 advertiser_id uuid not null,
 title text not null,
 target_url text,
 placement text not null default 'market',
 budget numeric(14,2) not null default 0,
 spent numeric(14,2) not null default 0,
 status text not null default 'pending',
 billing_status text not null default 'unbilled',
 impressions bigint not null default 0,
 clicks bigint not null default 0,
 starts_at timestamptz,
 ends_at timestamptz,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_ads_status_idx on public.koja_market_ads(status,placement);

create table if not exists public.koja_market_reviews (
 id uuid primary key default gen_random_uuid(),
 product_id uuid not null references public.koja_market_products(id) on delete cascade,
 buyer_id uuid not null,
 rating integer not null check(rating between 1 and 5),
 review text default '',
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(product_id,buyer_id)
);

-- Marketplace financial ledger: 10% KOJA / 90% seller.
create table if not exists public.koja_market_ledger (
 id uuid primary key default gen_random_uuid(),
 order_id uuid references public.koja_market_orders(id) on delete set null,
 seller_id uuid not null,
 buyer_id uuid,
 gross_amount numeric(14,2) not null default 0,
 commission_amount numeric(14,2) not null default 0,
 platform_fee numeric(14,2) not null default 0,
 net_amount numeric(14,2) not null default 0,
 currency text not null default 'ZMW',
 status text not null default 'pending',
 created_at timestamptz not null default now()
);
create unique index if not exists koja_market_ledger_order_uidx on public.koja_market_ledger(order_id) where order_id is not null;
create index if not exists koja_market_ledger_seller_idx on public.koja_market_ledger(seller_id,created_at desc);

create table if not exists public.koja_market_payouts (
 id uuid primary key default gen_random_uuid(),
 seller_id uuid not null,
 user_id uuid not null,
 amount numeric(14,2) not null check(amount>0),
 currency text not null default 'ZMW',
 method text not null default 'mobile_money',
 destination text not null,
 status text not null default 'requested',
 provider_reference text,
 admin_note text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_market_payouts_seller_idx on public.koja_market_payouts(seller_id,status,created_at desc);

-- Referrals.
create table if not exists public.koja_referral_codes (
 id uuid primary key default gen_random_uuid(),
 user_id uuid unique not null,
 code text unique not null,
 active boolean not null default true,
 created_at timestamptz not null default now()
);
create table if not exists public.koja_referrals (
 id uuid primary key default gen_random_uuid(),
 referrer_id uuid not null,
 referred_user_id uuid not null,
 code text not null,
 status text not null default 'registered',
 reward_amount numeric(14,2) not null default 0,
 created_at timestamptz not null default now(),
 unique(referrer_id,referred_user_id)
);
create index if not exists koja_referrals_referrer_idx on public.koja_referrals(referrer_id,created_at desc);

-- Useful order/payment indexes.
create index if not exists koja_market_orders_payment_reference_idx on public.koja_market_orders(payment_reference);
create index if not exists koja_market_orders_status_idx on public.koja_market_orders(status,created_at desc);

-- Keep the existing Business/POS and AI migrations compatible.
alter table if exists public.koja_ai_subscriptions add column if not exists monthly_price numeric(14,2) default 0;

-- Never modify Communications, WebRTC, FCM or LiveKit tables here.


-- ============================================================
-- SOURCE: KOJA_V12_V20_ALL_IN_ONE.sql
-- ============================================================
-- KOJA V12-V17 AFRICA ENGINE SUITE
-- Safe/idempotent additive migration. Does not alter Communications.

-- V12 Search / discovery indexes
create index if not exists koja_market_products_search_idx on public.koja_market_products (created_at desc);
create index if not exists koja_businesses_search_idx on public.koja_businesses (created_at desc);
create index if not exists service_providers_search_idx on public.service_providers (created_at desc);

-- V13 Ads Network
create table if not exists public.koja_v13_ad_campaigns (
 id uuid primary key default gen_random_uuid(), advertiser_id uuid not null, name text not null,
 placement text not null default 'search', daily_budget numeric(18,2) not null default 0,
 total_budget numeric(18,2) not null default 0, status text not null default 'draft',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_v13_ads_advertiser_idx on public.koja_v13_ad_campaigns(advertiser_id,created_at desc);
create table if not exists public.koja_v13_ad_events (
 id uuid primary key default gen_random_uuid(), campaign_id uuid not null, user_id uuid,
 event_type text not null default 'impression', metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
create index if not exists koja_v13_ad_events_campaign_idx on public.koja_v13_ad_events(campaign_id,created_at desc);

-- V14 Pay orchestration layer. Existing Flutterwave flows remain untouched.
create table if not exists public.koja_v14_payment_intents (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, amount numeric(18,2) not null check(amount>0),
 currency text not null default 'ZMW', purpose text not null, provider text not null default 'flutterwave',
 status text not null default 'pending', provider_reference text, metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_v14_pay_user_idx on public.koja_v14_payment_intents(user_id,created_at desc);

-- V15 Cloud / Developer
alter table if exists public.koja_api_keys add column if not exists name text default 'KOJA API Key';
alter table if exists public.koja_api_keys add column if not exists key_prefix text default '';
alter table if exists public.koja_api_keys add column if not exists status text default 'active';
alter table if exists public.koja_api_keys add column if not exists updated_at timestamptz default now();
alter table if exists public.koja_api_usage_events add column if not exists units integer default 1;

-- V16 Data & Intelligence
create table if not exists public.koja_v16_intelligence_events (
 id uuid primary key default gen_random_uuid(), source text not null, metric text not null,
 country_code text default 'ZM', value numeric(24,6) default 0, metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now()
);
create index if not exists koja_v16_intel_metric_idx on public.koja_v16_intelligence_events(metric,country_code,created_at desc);

-- V17 Identity & Trust
create table if not exists public.koja_v17_identity (
 id uuid primary key default gen_random_uuid(), user_id uuid not null unique, legal_name text not null default '',
 document_type text default '', document_number text default '', status text not null default 'unverified',
 verification_level text not null default 'basic', admin_note text default '',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_v17_identity_status_idx on public.koja_v17_identity(status,created_at desc);

-- Unified engine audit log
create table if not exists public.koja_engine_events (
 id uuid primary key default gen_random_uuid(), user_id uuid, engine text not null, action text not null,
 metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists koja_engine_events_engine_idx on public.koja_engine_events(engine,created_at desc);

-- ============================================================
-- KOJA V18 -> V20 ALL-IN-ONE EXTENSION
-- V18 Workspace + Enterprise
-- V19 Africa Super-App / Ecosystem Integration
-- V20 Autonomous Africa / Future Infrastructure
-- Safe/idempotent migration: CREATE IF NOT EXISTS / ADD IF NOT EXISTS
-- ============================================================

-- =========================
-- V18: WORKSPACE + ENTERPRISE
-- =========================
create table if not exists public.koja_workspaces (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null,
  name text not null,
  workspace_type text not null default 'business',
  plan text not null default 'free',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_workspaces_owner_idx on public.koja_workspaces(owner_id,created_at desc);

create table if not exists public.koja_workspace_members (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.koja_workspaces(id) on delete cascade,
  user_id uuid not null,
  role text not null default 'member',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  unique(workspace_id,user_id)
);
create index if not exists koja_workspace_members_user_idx on public.koja_workspace_members(user_id,created_at desc);

create table if not exists public.koja_workspace_files (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.koja_workspaces(id) on delete cascade,
  owner_id uuid not null,
  name text not null,
  storage_path text,
  mime_type text,
  size_bytes bigint default 0,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_workspace_files_ws_idx on public.koja_workspace_files(workspace_id,created_at desc);

create table if not exists public.koja_workspace_documents (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.koja_workspaces(id) on delete cascade,
  owner_id uuid not null,
  title text not null,
  content text default '',
  document_type text not null default 'document',
  version integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_workspace_documents_ws_idx on public.koja_workspace_documents(workspace_id,updated_at desc);

create table if not exists public.koja_enterprise_contracts (
  id uuid primary key default gen_random_uuid(),
  account_id uuid,
  customer_id uuid,
  contract_name text not null,
  plan text not null default 'enterprise',
  value numeric(18,2) not null default 0,
  currency text not null default 'USD',
  status text not null default 'lead',
  starts_at timestamptz,
  ends_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_enterprise_contracts_status_idx on public.koja_enterprise_contracts(status,created_at desc);

create table if not exists public.koja_enterprise_seats (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.koja_enterprise_contracts(id) on delete cascade,
  user_id uuid,
  seat_role text not null default 'user',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  unique(contract_id,user_id)
);

-- =========================
-- V19: SUPER-APP / ECOSYSTEM
-- =========================
create table if not exists public.koja_service_registry (
  id uuid primary key default gen_random_uuid(),
  service_key text not null unique,
  service_name text not null,
  category text not null,
  version text not null default '1.0',
  status text not null default 'active',
  api_base text,
  revenue_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.koja_service_registry(service_key,service_name,category) values
('search','KOJA Search','discovery'),
('ads','KOJA Ads','advertising'),
('pay','KOJA Pay','payments'),
('cloud','KOJA Cloud','infrastructure'),
('developer','KOJA Developer','developer'),
('data','KOJA Data Intelligence','analytics'),
('identity','KOJA Identity','trust'),
('workspace','KOJA Workspace','productivity'),
('enterprise','KOJA Enterprise','business'),
('market','KOJA Market','commerce'),
('logistics','KOJA Logistics','logistics'),
('ai','KOJA AI','artificial_intelligence')
on conflict(service_key) do nothing;

create table if not exists public.koja_user_service_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  service_key text not null,
  event_type text not null,
  object_id text,
  country_code text default 'ZM',
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists koja_user_service_events_user_idx on public.koja_user_service_events(user_id,created_at desc);
create index if not exists koja_user_service_events_service_idx on public.koja_user_service_events(service_key,created_at desc);

create table if not exists public.koja_ecosystem_links (
  id uuid primary key default gen_random_uuid(),
  source_service text not null,
  target_service text not null,
  link_type text not null default 'related',
  enabled boolean not null default true,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(source_service,target_service,link_type)
);

create table if not exists public.koja_unified_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  service_key text not null,
  external_reference text,
  amount numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  platform_fee numeric(18,2) not null default 0,
  status text not null default 'pending',
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_unified_transactions_user_idx on public.koja_unified_transactions(user_id,created_at desc);
create index if not exists koja_unified_transactions_service_idx on public.koja_unified_transactions(service_key,status,created_at desc);

-- =========================
-- V20: AUTONOMOUS AFRICA / FUTURE INFRASTRUCTURE
-- =========================
create table if not exists public.koja_ai_agents (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid,
  name text not null,
  agent_type text not null default 'general',
  status text not null default 'active',
  instructions text default '',
  tools jsonb not null default '[]'::jsonb,
  spending_limit numeric(18,2) not null default 0,
  currency text not null default 'ZMW',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_ai_agents_owner_idx on public.koja_ai_agents(owner_id,created_at desc);

create table if not exists public.koja_ai_agent_runs (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references public.koja_ai_agents(id) on delete cascade,
  owner_id uuid,
  task text not null,
  status text not null default 'queued',
  result jsonb default '{}'::jsonb,
  cost numeric(18,6) not null default 0,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);
create index if not exists koja_ai_agent_runs_agent_idx on public.koja_ai_agent_runs(agent_id,created_at desc);

create table if not exists public.koja_iot_devices (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid,
  device_key text not null unique,
  device_type text not null,
  name text not null,
  country_code text default 'ZM',
  latitude numeric(10,7),
  longitude numeric(10,7),
  status text not null default 'offline',
  metadata jsonb default '{}'::jsonb,
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_iot_devices_owner_idx on public.koja_iot_devices(owner_id,created_at desc);

create table if not exists public.koja_iot_telemetry (
  id uuid primary key default gen_random_uuid(),
  device_id uuid not null references public.koja_iot_devices(id) on delete cascade,
  metric text not null,
  value numeric,
  unit text,
  payload jsonb default '{}'::jsonb,
  recorded_at timestamptz not null default now()
);
create index if not exists koja_iot_telemetry_device_idx on public.koja_iot_telemetry(device_id,recorded_at desc);

create table if not exists public.koja_autonomy_jobs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid,
  job_type text not null,
  status text not null default 'queued',
  priority integer not null default 100,
  input jsonb default '{}'::jsonb,
  output jsonb default '{}'::jsonb,
  estimated_cost numeric(18,6) not null default 0,
  actual_cost numeric(18,6) not null default 0,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz
);
create index if not exists koja_autonomy_jobs_status_idx on public.koja_autonomy_jobs(status,priority,created_at);

create table if not exists public.koja_future_infrastructure (
  id uuid primary key default gen_random_uuid(),
  asset_type text not null,
  asset_name text not null,
  country_code text default 'ZM',
  status text not null default 'planned',
  latitude numeric(10,7),
  longitude numeric(10,7),
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists koja_future_infrastructure_country_idx on public.koja_future_infrastructure(country_code,asset_type,status);

-- Common platform metadata
alter table if exists public.profiles add column if not exists koja_id text;
alter table if exists public.profiles add column if not exists verification_level text default 'basic';
alter table if exists public.profiles add column if not exists default_country_code text default 'ZM';
create unique index if not exists profiles_koja_id_unique_idx on public.profiles(koja_id) where koja_id is not null;

-- V20 revenue/event foundation
create table if not exists public.koja_engine_revenue (
  id uuid primary key default gen_random_uuid(),
  service_key text not null,
  revenue_type text not null,
  amount numeric(18,2) not null default 0,
  currency text not null default 'USD',
  reference_id text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists koja_engine_revenue_service_idx on public.koja_engine_revenue(service_key,created_at desc);

-- ============================================================
-- END KOJA V12 -> V20 ALL-IN-ONE
-- ============================================================


-- ============================================================
-- SOURCE: KOJA_AI_ALL_CORE_V3_SINGLE.sql
-- ============================================================
-- ============================================================
-- KOJA AI ALL-IN-ONE CORE V3 SQL
-- Memory V2 + Core V1 + Core V2 + Core V3
-- Additive/idempotent migration. Does not drop or recreate KOJA data tables.
-- Run this single file in Supabase SQL Editor.
-- ============================================================

-- MEMORY V2
-- KOJA AI Memory V2
-- Additive/idempotent migration. Does not drop or recreate existing KOJA tables.
-- Run once in the Supabase SQL Editor.

create table if not exists public.koja_ai_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  memory text not null,
  category text not null default 'general',
  importance integer not null default 7 check (importance between 1 and 10),
  source text not null default 'explicit',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists koja_ai_memories_user_active_idx
  on public.koja_ai_memories(user_id, is_active, updated_at desc);
create index if not exists koja_ai_memories_user_memory_idx
  on public.koja_ai_memories(user_id, memory);

alter table public.koja_ai_memories enable row level security;
drop policy if exists "Users can read own AI memories" on public.koja_ai_memories;
create policy "Users can read own AI memories" on public.koja_ai_memories for select using (auth.uid() = user_id);
drop policy if exists "Users can insert own AI memories" on public.koja_ai_memories;
create policy "Users can insert own AI memories" on public.koja_ai_memories for insert with check (auth.uid() = user_id);
drop policy if exists "Users can update own AI memories" on public.koja_ai_memories;
create policy "Users can update own AI memories" on public.koja_ai_memories for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "Users can delete own AI memories" on public.koja_ai_memories;
create policy "Users can delete own AI memories" on public.koja_ai_memories for delete using (auth.uid() = user_id);

create table if not exists public.koja_ai_file_memory (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  file_name text not null,
  content text not null,
  content_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists koja_ai_file_memory_user_hash_uidx
  on public.koja_ai_file_memory(user_id, content_hash);
create index if not exists koja_ai_file_memory_user_updated_idx
  on public.koja_ai_file_memory(user_id, updated_at desc);

alter table public.koja_ai_file_memory enable row level security;
drop policy if exists "Users can read own AI file memory" on public.koja_ai_file_memory;
create policy "Users can read own AI file memory" on public.koja_ai_file_memory for select using (auth.uid() = user_id);
drop policy if exists "Users can insert own AI file memory" on public.koja_ai_file_memory;
create policy "Users can insert own AI file memory" on public.koja_ai_file_memory for insert with check (auth.uid() = user_id);
drop policy if exists "Users can update own AI file memory" on public.koja_ai_file_memory;
create policy "Users can update own AI file memory" on public.koja_ai_file_memory for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "Users can delete own AI file memory" on public.koja_ai_file_memory;
create policy "Users can delete own AI file memory" on public.koja_ai_file_memory for delete using (auth.uid() = user_id);


-- CORE V1
-- KOJA AI CORE V1
-- Additive/idempotent migration. Does not drop or recreate existing KOJA AI tables.

create extension if not exists pgcrypto;

create table if not exists public.koja_ai_core_knowledge (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  content text not null,
  source text default 'koja-core',
  is_verified boolean not null default false,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.koja_ai_core_learnings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  learning text not null,
  source text default 'user',
  is_verified boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.koja_ai_core_tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  task_type text not null,
  prompt text,
  result text,
  provider text,
  status text default 'ok',
  metadata text default '{}',
  created_at timestamptz not null default now()
);

create table if not exists public.koja_ai_provider_health (
  id uuid primary key default gen_random_uuid(),
  provider text unique not null,
  status text default 'unknown',
  failure_count integer not null default 0,
  last_error text default '',
  last_checked_at timestamptz,
  last_success_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.koja_ai_evaluations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  task_id uuid references public.koja_ai_core_tasks(id) on delete set null,
  score numeric,
  feedback text,
  is_verified boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_koja_ai_core_knowledge_active on public.koja_ai_core_knowledge(is_active, updated_at desc);
create index if not exists idx_koja_ai_core_learnings_user on public.koja_ai_core_learnings(user_id, created_at desc);
create index if not exists idx_koja_ai_core_tasks_user on public.koja_ai_core_tasks(user_id, created_at desc);
create index if not exists idx_koja_ai_evaluations_user on public.koja_ai_evaluations(user_id, created_at desc);

alter table public.koja_ai_core_knowledge enable row level security;
alter table public.koja_ai_core_learnings enable row level security;
alter table public.koja_ai_core_tasks enable row level security;
alter table public.koja_ai_provider_health enable row level security;
alter table public.koja_ai_evaluations enable row level security;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_knowledge' and policyname='koja_core_knowledge_select') then
    create policy koja_core_knowledge_select on public.koja_ai_core_knowledge for select to authenticated using (is_active = true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_learnings' and policyname='koja_core_learnings_owner') then
    create policy koja_core_learnings_owner on public.koja_ai_core_learnings for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_tasks' and policyname='koja_core_tasks_owner') then
    create policy koja_core_tasks_owner on public.koja_ai_core_tasks for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_provider_health' and policyname='koja_core_provider_health_select') then
    create policy koja_core_provider_health_select on public.koja_ai_provider_health for select to authenticated using (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_evaluations' and policyname='koja_core_evaluations_owner') then
    create policy koja_core_evaluations_owner on public.koja_ai_evaluations for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
end $$;

-- Optional starter knowledge can be inserted later after deployment.


-- CORE V2
create extension if not exists pgcrypto;
create table if not exists public.koja_ai_core_graph (
  id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete cascade,
  entity text not null, entity_type text not null default 'concept', relation text not null, target text not null,
  source text default 'koja-core', confidence numeric default 0.5, is_verified boolean not null default false,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_koja_ai_core_graph_user on public.koja_ai_core_graph(user_id, updated_at desc);
create index if not exists idx_koja_ai_core_graph_entity on public.koja_ai_core_graph(entity, target);
alter table public.koja_ai_provider_health add column if not exists cooldown_until timestamptz;
create table if not exists public.koja_ai_core_tools (
  id uuid primary key default gen_random_uuid(), name text unique not null, description text not null,
  tool_type text not null default 'deterministic', recipe text default '', is_active boolean not null default true,
  is_verified boolean not null default false, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.koja_ai_core_proposals (
  id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete cascade,
  proposal text not null, reason text default '', proposed_change text default '', status text not null default 'proposed',
  created_at timestamptz not null default now(), reviewed_at timestamptz
);
create index if not exists idx_koja_ai_core_proposals_user on public.koja_ai_core_proposals(user_id, created_at desc);
alter table public.koja_ai_core_graph enable row level security;
alter table public.koja_ai_core_tools enable row level security;
alter table public.koja_ai_core_proposals enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_select_own') then
    create policy koja_core_graph_select_own on public.koja_ai_core_graph for select to authenticated using (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_insert_own') then
    create policy koja_core_graph_insert_own on public.koja_ai_core_graph for insert to authenticated with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_update_own') then
    create policy koja_core_graph_update_own on public.koja_ai_core_graph for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_delete_own') then
    create policy koja_core_graph_delete_own on public.koja_ai_core_graph for delete to authenticated using (user_id = auth.uid());
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_tools' and policyname='koja_core_tools_select') then
    create policy koja_core_tools_select on public.koja_ai_core_tools for select to authenticated using (is_active = true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_proposals' and policyname='koja_core_proposals_owner') then
    create policy koja_core_proposals_owner on public.koja_ai_core_proposals for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
  end if;
end $$;
insert into public.koja_ai_core_tools(name,description,tool_type,recipe,is_active,is_verified) values
 ('calculator','Safe arithmetic and percentage calculations without executing arbitrary code.','deterministic','restricted_ast_arithmetic',true,true),
 ('word_count','Count words in explicitly supplied text.','deterministic','split_whitespace',true,true),
 ('retrieval','Retrieve signed-in user memory, previous conversations and stored file text.','retrieval','core_v2_semantic_retrieval',true,true)
on conflict (name) do update set description=excluded.description, recipe=excluded.recipe, updated_at=now();


-- CORE V3
create extension if not exists pgcrypto;
create table if not exists public.koja_ai_core_graph (
  id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete cascade,
  entity text not null, entity_type text not null default 'concept', relation text not null, target text not null,
  source text default 'core', confidence numeric default 0.5, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_koja_ai_core_graph_user on public.koja_ai_core_graph(user_id, updated_at desc);
create index if not exists idx_koja_ai_core_graph_entity on public.koja_ai_core_graph(entity, target);
alter table public.koja_ai_core_graph enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_select_own') then create policy koja_core_graph_select_own on public.koja_ai_core_graph for select using (auth.uid()=user_id); end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_insert_own') then create policy koja_core_graph_insert_own on public.koja_ai_core_graph for insert with check (auth.uid()=user_id); end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_update_own') then create policy koja_core_graph_update_own on public.koja_ai_core_graph for update using (auth.uid()=user_id) with check (auth.uid()=user_id); end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_graph' and policyname='koja_core_graph_delete_own') then create policy koja_core_graph_delete_own on public.koja_ai_core_graph for delete using (auth.uid()=user_id); end if;
end $$;
alter table public.koja_ai_provider_health add column if not exists cooldown_until timestamptz;
alter table public.koja_ai_provider_health add column if not exists total_requests integer not null default 0;
alter table public.koja_ai_provider_health add column if not exists total_failures integer not null default 0;
create table if not exists public.koja_ai_core_semantic_cache (
  id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete cascade,
  query_text text not null, result jsonb not null default '[]'::jsonb, engine text not null default 'core-v3-hash',
  created_at timestamptz not null default now(), expires_at timestamptz
);
create index if not exists idx_koja_ai_core_semantic_cache_user on public.koja_ai_core_semantic_cache(user_id, created_at desc);
alter table public.koja_ai_core_semantic_cache enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_semantic_cache' and policyname='koja_core_cache_select_own') then create policy koja_core_cache_select_own on public.koja_ai_core_semantic_cache for select using (auth.uid()=user_id); end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_semantic_cache' and policyname='koja_core_cache_insert_own') then create policy koja_core_cache_insert_own on public.koja_ai_core_semantic_cache for insert with check (auth.uid()=user_id); end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='koja_ai_core_semantic_cache' and policyname='koja_core_cache_delete_own') then create policy koja_core_cache_delete_own on public.koja_ai_core_semantic_cache for delete using (auth.uid()=user_id); end if;
end $$;


-- ============================================================
-- SOURCE: KOJA_LIVE_SETUP.sql
-- ============================================================
-- KOJA AFRICA LIVE DELIVERY SETUP
-- Run in Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.driver_locations (
    id uuid primary key default gen_random_uuid(),
    driver_id uuid,
    user_id uuid,
    latitude double precision not null,
    longitude double precision not null,
    accuracy double precision,
    speed double precision,
    heading double precision,
    altitude double precision,
    is_online boolean default true,
    created_at timestamptz default now()
);

create index if not exists driver_locations_driver_id_idx on public.driver_locations(driver_id);
create index if not exists driver_locations_user_id_idx on public.driver_locations(user_id);
create index if not exists driver_locations_created_at_idx on public.driver_locations(created_at desc);
create index if not exists driver_locations_online_idx on public.driver_locations(is_online);

create table if not exists public.deliveries (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid,
    driver_id uuid,
    pickup_address text not null,
    delivery_address text not null,
    pickup_latitude double precision,
    pickup_longitude double precision,
    status text not null default 'requested',
    tracking_code text unique not null,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists deliveries_driver_id_idx on public.deliveries(driver_id);
create index if not exists deliveries_customer_id_idx on public.deliveries(customer_id);
create index if not exists deliveries_tracking_code_idx on public.deliveries(tracking_code);
create index if not exists deliveries_status_idx on public.deliveries(status);

-- If your project already has these tables, do not recreate them.
-- The live app uses your existing driver_profiles, assignments,
-- professional_bookings, doctor_profiles, teacher_profiles, cvs and farmers tables.


-- ============================================================
-- SOURCE: KOJA_DELIVERY_OTP_VERIFICATION_20260912.sql
-- ============================================================
-- KOJA DELIVERY OTP VERIFICATION HARDENING
-- Additive only. No table recreation or destructive changes.

alter table public.deliveries
  add column if not exists delivery_confirmation_attempts integer not null default 0,
  add column if not exists delivery_confirmation_locked boolean not null default false;

create index if not exists idx_koja_deliveries_confirmation_lock
  on public.deliveries (tracking_code, delivery_confirmation_locked, delivery_confirmation_verified);

update public.deliveries set delivery_confirmation_attempts = 0 where delivery_confirmation_attempts is null;
update public.deliveries set delivery_confirmation_locked = false where delivery_confirmation_locked is null;

select tracking_code, delivery_confirmation_verified, delivery_confirmation_attempts, delivery_confirmation_locked, status
from public.deliveries order by created_at desc limit 20;


-- ============================================================
-- CURRENT KOJA DOCUMENT AI + LEARNING MIGRATION
-- ============================================================
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
create unique index if not exists uq_koja_document_ai_index_document_id on public.koja_document_ai_index(document_id);
create index if not exists idx_koja_document_ai_index_user_id on public.koja_document_ai_index(user_id);
create index if not exists idx_koja_document_ai_index_status on public.koja_document_ai_index(status);

create table if not exists public.koja_document_learning_progress (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null, user_id uuid not null,
  action text not null default 'study', score numeric, total numeric, notes text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
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
  id uuid primary key default gen_random_uuid(), document_id uuid not null, user_id uuid not null,
  memory_type text not null default 'learning', content text not null,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.koja_document_ai_memory add column if not exists document_id uuid;
alter table public.koja_document_ai_memory add column if not exists user_id uuid;
alter table public.koja_document_ai_memory add column if not exists memory_type text not null default 'learning';
alter table public.koja_document_ai_memory add column if not exists content text;
alter table public.koja_document_ai_memory add column if not exists created_at timestamptz not null default now();
alter table public.koja_document_ai_memory add column if not exists updated_at timestamptz not null default now();
create index if not exists idx_koja_doc_ai_memory_document_user on public.koja_document_ai_memory(document_id,user_id,created_at desc);

-- Physical Market automatic driver request
alter table public.koja_market_orders add column if not exists auto_driver_request boolean not null default true;
create index if not exists idx_koja_market_orders_auto_driver_request on public.koja_market_orders(auto_driver_request,status,created_at desc);

-- Push subscription compatibility
alter table public.koja_push_subscriptions add column if not exists subscription jsonb;
alter table public.koja_push_subscriptions add column if not exists user_id uuid;
alter table public.koja_push_subscriptions add column if not exists endpoint text;
alter table public.koja_push_subscriptions add column if not exists p256dh text;
alter table public.koja_push_subscriptions add column if not exists auth text;
create index if not exists idx_koja_push_subscriptions_user_id on public.koja_push_subscriptions(user_id);

-- Business orders compatibility
create table if not exists public.koja_business_orders (
  id uuid primary key default gen_random_uuid(), business_id uuid, buyer_id uuid,
  order_number text, status text default 'pending', total_amount numeric default 0, currency text default 'ZMW',
  items jsonb default '[]'::jsonb, customer_name text, customer_phone text, customer_address text,
  payment_reference text, payment_status text default 'pending', created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.koja_business_orders add column if not exists business_id uuid;
alter table public.koja_business_orders add column if not exists buyer_id uuid;
alter table public.koja_business_orders add column if not exists order_number text;
alter table public.koja_business_orders add column if not exists status text default 'pending';
alter table public.koja_business_orders add column if not exists total_amount numeric default 0;
alter table public.koja_business_orders add column if not exists currency text default 'ZMW';
alter table public.koja_business_orders add column if not exists items jsonb default '[]'::jsonb;
alter table public.koja_business_orders add column if not exists customer_name text;
alter table public.koja_business_orders add column if not exists customer_phone text;
alter table public.koja_business_orders add column if not exists customer_address text;
alter table public.koja_business_orders add column if not exists payment_reference text;
alter table public.koja_business_orders add column if not exists payment_status text default 'pending';
alter table public.koja_business_orders add column if not exists created_at timestamptz not null default now();
alter table public.koja_business_orders add column if not exists updated_at timestamptz not null default now();
create index if not exists idx_koja_business_orders_business on public.koja_business_orders(business_id,created_at desc);
create index if not exists idx_koja_business_orders_buyer on public.koja_business_orders(buyer_id,created_at desc);
create index if not exists idx_koja_business_orders_payment_ref on public.koja_business_orders(payment_reference);

-- ============================================================
-- END KOJA MASTER SQL
-- ============================================================
