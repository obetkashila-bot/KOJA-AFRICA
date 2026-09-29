-- KOJA NEWS Studio Assets — additive migration
create extension if not exists pgcrypto;

alter table public.koja_news_live add column if not exists background_asset_id uuid;
alter table public.koja_news_live add column if not exists desk_asset_id uuid;
alter table public.koja_news_live add column if not exists desk_url text not null default '';

create table if not exists public.koja_news_studio_assets (
 id uuid primary key default gen_random_uuid(),
 name text not null,
 asset_type text not null check(asset_type in ('background','desk')),
 scene_slug text not null default 'main_desk',
 storage_path text not null,
 public_url text not null,
 mime_type text not null default 'application/octet-stream',
 file_size bigint not null default 0,
 created_by uuid,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);

create index if not exists koja_news_studio_assets_type_idx
 on public.koja_news_studio_assets(asset_type,scene_slug,created_at desc);
