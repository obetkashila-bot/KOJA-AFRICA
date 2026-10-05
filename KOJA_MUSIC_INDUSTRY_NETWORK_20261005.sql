-- KOJA MUSIC GLOBAL INDUSTRY NETWORK
-- Additive only. No DROP/TRUNCATE/DELETE.
create extension if not exists pgcrypto;

create table if not exists public.koja_music_industries (
  id uuid primary key default gen_random_uuid(),
  region text not null,
  country text not null,
  name text not null,
  industry_type text,
  website text,
  description text,
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists koja_music_industries_region_idx on public.koja_music_industries(region,country);
create unique index if not exists koja_music_industries_unique_idx on public.koja_music_industries(region,country,name);

-- Optional future catalogue of industry-supplied/authorized videos.
create table if not exists public.koja_music_industry_videos (
  id uuid primary key default gen_random_uuid(),
  industry_id uuid references public.koja_music_industries(id) on delete set null,
  title text not null,
  description text,
  video_url text not null,
  thumbnail_url text,
  source_type text default 'authorized',
  rights_status text default 'authorized',
  status text default 'published',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists koja_music_industry_videos_industry_idx on public.koja_music_industry_videos(industry_id,status,created_at desc);

alter table public.koja_music_artists add column if not exists industry_region text;
alter table public.koja_music_artists add column if not exists industry_country text;
alter table public.koja_music_artists add column if not exists recruitment_status text default 'active';

alter table public.koja_music_tracks add column if not exists industry_id uuid references public.koja_music_industries(id) on delete set null;
alter table public.koja_music_tracks add column if not exists external_video_url text;
alter table public.koja_music_tracks add column if not exists external_video_provider text;
create index if not exists koja_music_tracks_industry_idx on public.koja_music_tracks(industry_id,status,created_at desc);

-- Safe seed. The application also retries these records if the table is initially empty.
insert into public.koja_music_industries(region,country,name,industry_type,website,description)
select * from (values
('Africa','Zambia','ZAMCOPS','Collecting Society','https://zamcops.org/','Rights, licensing and creator representation'),
('Africa','South Africa','Recording Industry of South Africa (RISA)','Industry Association','https://risa.org.za/','Recording-industry representation and information'),
('Africa','Kenya','Recording Industry of Kenya (RIKE)','Industry Association','https://www.rike.or.ke/','Recording industry and rights information'),
('Africa','Nigeria','IFPI Sub-Saharan Africa','Regional Industry','https://www.ifpi.org/','Regional recording-industry information and licensing'),
('Africa','Uganda','Uganda Performing Right Society (UPRS)','Collecting Society','https://www.uprs.go.ug/','Creator rights and licensing'),
('Asia','India','Indian Music Industry (IMI)','Industry Association','https://indianmi.org/','Recording-industry representation and ISRC information'),
('Asia','Japan','Recording Industry Association of Japan (RIAJ)','Industry Association','https://www.riaj.or.jp/','Recording-industry and rights information'),
('Asia','South Korea','Korea Music Content Association (KMCA)','Industry Association','https://www.k-mca.or.kr/','Music-content industry information'),
('Asia','Malaysia','Recording Industry Association of Malaysia (RIM)','Industry Association','https://www.rim.org.my/','Recording-industry information'),
('Asia','Singapore','Recording Industry Association (Singapore) (RIAS)','Industry Association','https://www.rias.org.sg/','Recording-industry information'),
('Americas','United States','Recording Industry Association of America (RIAA)','Industry Association','https://www.riaa.com/','Recording-industry and rights information'),
('Americas','Canada','Re:Sound','Collecting Society','https://www.resound.ca/','Neighbouring-rights licensing and information'),
('Americas','Mexico','SOMEXFON','Collecting Society','https://somexfon.com/','Music licensing and rights information'),
('Americas','Brazil','ABRAMUS','Collecting Society','https://www.abramus.org.br/','Music rights and creator representation'),
('Americas','Argentina','CAPIF','Industry Association','https://www.capif.org.ar/','Recording-industry information'),
('Americas','Jamaica','JAMMS','Collecting Society','https://jammsonline.com/','Music rights and licensing'),
('Global','Global','IFPI','Global Recording Industry','https://www.ifpi.org/','Global recording-industry data, licensing and rights'),
('Global','Global','YouTube for Artists','Artist Platform','https://artists.youtube/','Official artist-channel and music-video resources')
) as v(region,country,name,industry_type,website,description)
where not exists (
  select 1 from public.koja_music_industries i where i.region=v.region and i.country=v.country and i.name=v.name
);
