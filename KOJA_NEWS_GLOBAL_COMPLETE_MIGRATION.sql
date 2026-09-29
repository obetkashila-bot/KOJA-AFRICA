-- KOJA NEWS GLOBAL — additive migration, no node architecture
alter table public.koja_public_posts add column if not exists country text default 'Global';
alter table public.koja_public_posts add column if not exists region text default '';
alter table public.koja_public_posts add column if not exists city text default '';
alter table public.koja_public_posts add column if not exists language text default 'English';
alter table public.koja_public_posts add column if not exists category text default 'General';
alter table public.koja_public_posts add column if not exists subcategory text default '';
alter table public.koja_public_posts add column if not exists publisher text default '';
alter table public.koja_public_posts add column if not exists reporter text default '';
alter table public.koja_public_posts add column if not exists source_name text default '';
alter table public.koja_public_posts add column if not exists source_url text default '';

update public.koja_public_posts set country='Global' where country is null or country='';
update public.koja_public_posts set language='English' where language is null or language='';
update public.koja_public_posts set category='General' where category is null or category='';

create index if not exists koja_public_posts_news_country_idx on public.koja_public_posts(post_type,country,created_at desc);
create index if not exists koja_public_posts_news_category_idx on public.koja_public_posts(post_type,category,created_at desc);
create index if not exists koja_public_posts_news_region_idx on public.koja_public_posts(post_type,region,created_at desc);

-- Existing Live Studio columns; safe if already present.
alter table public.koja_news_live add column if not exists scene_slug text default 'main_desk';
alter table public.koja_news_live add column if not exists presenter_name text default '';
alter table public.koja_news_live add column if not exists guest_name text default '';
alter table public.koja_news_live add column if not exists guest_title text default '';
alter table public.koja_news_live add column if not exists wall_headline text default '';
alter table public.koja_news_live add column if not exists wall_subtitle text default '';
alter table public.koja_news_live add column if not exists breaking boolean default false;
alter table public.koja_news_live add column if not exists country text default '';
alter table public.koja_news_live add column if not exists region text default '';
alter table public.koja_news_live add column if not exists language text default 'English';
alter table public.koja_news_live add column if not exists timezone text default 'UTC';
alter table public.koja_news_live add column if not exists network_name text default 'KOJA NEWS';
alter table public.koja_news_live add column if not exists studio_updated_at timestamptz;
