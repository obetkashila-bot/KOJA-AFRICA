-- KOJA NEWS Studio Assets
create extension if not exists pgcrypto;
create table if not exists public.koja_news_studio_assets (
 id uuid primary key default gen_random_uuid(),
 name text not null,
 asset_type text not null check (asset_type in ('background','desk')),
 scene_slug text not null default 'main_desk',
 storage_path text not null,
 public_url text not null,
 mime_type text not null default 'image/png',
 created_by uuid,
 created_at timestamptz not null default now()
);
alter table public.koja_news_live add column if not exists background_asset_url text not null default '';
alter table public.koja_news_live add column if not exists desk_asset_url text not null default '';
alter table public.koja_news_live add column if not exists background_asset_id uuid;
alter table public.koja_news_live add column if not exists desk_asset_id uuid;
create index if not exists koja_news_studio_assets_scene_idx on public.koja_news_studio_assets(scene_slug,asset_type,created_at desc);
