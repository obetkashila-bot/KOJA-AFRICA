create table if not exists public.koja_contacts (
 id uuid primary key default gen_random_uuid(), requester_id uuid not null, addressee_id uuid not null,
 status text not null default 'pending', created_at timestamptz default now(), updated_at timestamptz default now(),
 unique(requester_id, addressee_id)
);
create index if not exists koja_contacts_requester_idx on public.koja_contacts(requester_id, status);
create index if not exists koja_contacts_addressee_idx on public.koja_contacts(addressee_id, status);
create table if not exists public.koja_conversations (
 id uuid primary key default gen_random_uuid(), conversation_type text not null default 'direct', created_by uuid,
 name text, avatar_url text, created_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_conversation_members (
 conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 user_id uuid not null, role text not null default 'member', joined_at timestamptz default now(), last_read_at timestamptz,
 muted boolean default false, primary key(conversation_id,user_id)
);
create index if not exists koja_members_user_idx on public.koja_conversation_members(user_id, conversation_id);
create table if not exists public.koja_messages (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 sender_id uuid not null, message_type text not null default 'text', body text default '', file_url text,
 created_at timestamptz default now(), edited_at timestamptz, deleted_at timestamptz
);
create index if not exists koja_messages_conversation_idx on public.koja_messages(conversation_id, created_at);
create table if not exists public.koja_calls (
 id uuid primary key default gen_random_uuid(), conversation_id uuid not null references public.koja_conversations(id) on delete cascade,
 caller_id uuid not null, callee_id uuid not null, mode text not null default 'video', status text not null default 'ringing',
 offer text, answer text, caller_ice jsonb default '[]'::jsonb, callee_ice jsonb default '[]'::jsonb,
 created_at timestamptz default now(), answered_at timestamptz, ended_at timestamptz
);
create index if not exists koja_calls_callee_idx on public.koja_calls(callee_id,status,created_at desc);
create index if not exists koja_calls_caller_idx on public.koja_calls(caller_id,status,created_at desc);
create table if not exists public.koja_presence (
 user_id uuid primary key, is_online boolean default false, last_seen_at timestamptz default now(), updated_at timestamptz default now()
);
create table if not exists public.koja_statuses (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, text_content text default '', media_url text,
 media_type text default 'text', visibility text not null default 'contacts',
 expires_at timestamptz not null default (now()+interval '24 hours'), created_at timestamptz default now()
);
create index if not exists koja_statuses_user_idx on public.koja_statuses(user_id,created_at desc);
create table if not exists public.koja_notifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null, notification_type text, title text, body text, related_id uuid,
 is_read boolean default false, created_at timestamptz default now()
);
create index if not exists koja_notifications_user_idx on public.koja_notifications(user_id,is_read,created_at desc);
create table if not exists public.koja_blocks (
 blocker_id uuid not null, blocked_id uuid not null, created_at timestamptz default now(), primary key(blocker_id,blocked_id)
);


-- ============================================================
-- PROFESSION-SPECIFIC + PUBLIC COMMUNICATION
-- One public communication room and public posts for EVERY profession.
-- GET pages can be publicly viewed; posting requires a logged-in KOJA account.
-- ============================================================
create table if not exists public.professional_public_messages (
 id uuid primary key default gen_random_uuid(),
 profession text not null, sender_id uuid not null, message text not null,
 created_at timestamptz default now(), deleted_at timestamptz
);
create index if not exists professional_public_messages_profession_idx
 on public.professional_public_messages(profession, created_at desc);

create table if not exists public.professional_public_posts (
 id uuid primary key default gen_random_uuid(),
 profession text not null, author_id uuid not null, provider_id uuid,
 title text not null, body text not null, media_url text,
 created_at timestamptz default now(), updated_at timestamptz default now()
);
create index if not exists professional_public_posts_profession_idx
 on public.professional_public_posts(profession, created_at desc);

create table if not exists public.professional_public_comments (
 id uuid primary key default gen_random_uuid(),
 post_id uuid not null references public.professional_public_posts(id) on delete cascade,
 author_id uuid not null, body text not null, created_at timestamptz default now()
);
create index if not exists professional_public_comments_post_idx
 on public.professional_public_comments(post_id, created_at);
