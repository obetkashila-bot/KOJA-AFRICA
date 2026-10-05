-- ============================================================
-- KOJA MUSIC — WHATSAPP ARTIST RECRUITMENT AUTOMATION
-- Additive / idempotent migration. Does not remove or replace
-- existing KOJA MUSIC tables or recruitment prospects.
-- ============================================================

alter table if exists public.koja_music_recruitment_targets
    add column if not exists whatsapp_phone text;
alter table if exists public.koja_music_recruitment_targets
    add column if not exists contact_phone text;
alter table if exists public.koja_music_recruitment_targets
    add column if not exists contact_verified boolean not null default false;
alter table if exists public.koja_music_recruitment_targets
    add column if not exists contact_source text;
alter table if exists public.koja_music_recruitment_targets
    add column if not exists contact_verified_at timestamptz;

create index if not exists koja_music_recruitment_targets_whatsapp_idx
    on public.koja_music_recruitment_targets(whatsapp_phone);

create table if not exists public.koja_music_outreach_campaigns (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    status text not null default 'draft' check (status in ('draft','approved','active','paused','completed','cancelled')),
    countries jsonb not null default '[]'::jsonb,
    priority_max integer not null default 2,
    created_by uuid,
    approved_by uuid,
    approved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists koja_music_outreach_campaigns_status_idx
    on public.koja_music_outreach_campaigns(status, created_at desc);

create table if not exists public.koja_music_outreach (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid references public.koja_music_outreach_campaigns(id) on delete cascade,
    artist_id uuid references public.koja_music_recruitment_targets(id) on delete set null,
    artist_name text not null,
    country text,
    whatsapp_phone text,
    status text not null default 'pending_approval' check (status in ('pending_approval','approved','sent','followup_sent','replied','interested','declined','failed','onboarding','rights_review','completed','approved_for_publication')),
    initial_sent_at timestamptz,
    last_sent_at timestamptz,
    last_provider_message_id text,
    last_inbound_at timestamptz,
    last_inbound_message text,
    replied_at timestamptz,
    followup3_due_at timestamptz,
    followup3_sent_at timestamptz,
    followup7_due_at timestamptz,
    followup7_sent_at timestamptz,
    onboarding_id uuid,
    onboarding_completed_at timestamptz,
    rights_verified_at timestamptz,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists koja_music_outreach_campaign_artist_uq
    on public.koja_music_outreach(campaign_id, artist_id)
    where campaign_id is not null and artist_id is not null;
create index if not exists koja_music_outreach_status_idx
    on public.koja_music_outreach(status, created_at asc);
create index if not exists koja_music_outreach_phone_idx
    on public.koja_music_outreach(whatsapp_phone);
create index if not exists koja_music_outreach_followup3_idx
    on public.koja_music_outreach(followup3_due_at)
    where followup3_due_at is not null;
create index if not exists koja_music_outreach_followup7_idx
    on public.koja_music_outreach(followup7_due_at)
    where followup7_due_at is not null;

create table if not exists public.koja_music_outreach_messages (
    id uuid primary key default gen_random_uuid(),
    outreach_id uuid not null references public.koja_music_outreach(id) on delete cascade,
    direction text not null check (direction in ('inbound','outbound')),
    message_type text not null default 'text',
    status text not null default 'received',
    provider_message_id text,
    provider_status text,
    payload jsonb not null default '{}'::jsonb,
    error_message text,
    sent_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists koja_music_outreach_messages_outreach_idx
    on public.koja_music_outreach_messages(outreach_id, created_at desc);
create unique index if not exists koja_music_outreach_messages_provider_id_uq
    on public.koja_music_outreach_messages(provider_message_id)
    where provider_message_id is not null;

create table if not exists public.koja_music_outreach_events (
    id uuid primary key default gen_random_uuid(),
    outreach_id uuid not null references public.koja_music_outreach(id) on delete cascade,
    event_type text not null,
    message_id text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists koja_music_outreach_events_outreach_idx
    on public.koja_music_outreach_events(outreach_id, created_at desc);
create index if not exists koja_music_outreach_events_message_idx
    on public.koja_music_outreach_events(message_id);

create table if not exists public.koja_music_artist_onboarding (
    id uuid primary key default gen_random_uuid(),
    outreach_id uuid references public.koja_music_outreach(id) on delete cascade,
    artist_id uuid references public.koja_music_recruitment_targets(id) on delete set null,
    token text not null unique,
    status text not null default 'invited' check (status in ('invited','started','submitted','needs_correction','approved','rejected')),
    artist_name text,
    legal_name text,
    country text,
    city text,
    phone text,
    email text,
    genres jsonb not null default '[]'::jsonb,
    bio text,
    catalogue_links jsonb not null default '[]'::jsonb,
    master_ownership text,
    composition_ownership text,
    rightsholder_declaration boolean not null default false,
    documents jsonb not null default '[]'::jsonb,
    submitted_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists koja_music_artist_onboarding_status_idx
    on public.koja_music_artist_onboarding(status, created_at desc);
create index if not exists koja_music_artist_onboarding_outreach_idx
    on public.koja_music_artist_onboarding(outreach_id);

create table if not exists public.koja_music_rights_reviews (
    id uuid primary key default gen_random_uuid(),
    onboarding_id uuid references public.koja_music_artist_onboarding(id) on delete cascade,
    artist_id uuid references public.koja_music_recruitment_targets(id) on delete set null,
    outreach_id uuid references public.koja_music_outreach(id) on delete set null,
    status text not null default 'pending' check (status in ('pending','verified','needs_correction','rejected','revoked')),
    master_rights text,
    composition_rights text,
    documents_verified boolean not null default false,
    notes text,
    reviewed_by uuid,
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists koja_music_rights_reviews_status_idx
    on public.koja_music_rights_reviews(status, created_at desc);
create index if not exists koja_music_rights_reviews_artist_idx
    on public.koja_music_rights_reviews(artist_id);

-- Keep the original recruitment target table authoritative. This only records
-- outreach metadata; it does not grant music, master, publishing or distribution rights.
-- Before live outreach, verify that each WhatsApp number was publicly supplied
-- for business/contact purposes and that the campaign message/template complies
-- with Meta's current WhatsApp Business requirements.
