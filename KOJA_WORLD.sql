-- KOJA WORLD public-services gateway
create table if not exists public.koja_world_services (
  id uuid primary key default gen_random_uuid(),
  country_code text not null,
  country_name text not null,
  service_name text not null,
  category text not null default 'Other',
  description text default '',
  url text not null default '',
  access_mode text not null default 'embed_or_external',
  is_active boolean not null default true,
  is_verified boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists koja_world_country_idx
  on public.koja_world_services(country_code, is_active);

create index if not exists koja_world_category_idx
  on public.koja_world_services(category, is_active);

create index if not exists koja_world_verified_idx
  on public.koja_world_services(is_verified, is_active);

-- Verified public destinations initially seeded from official provider sites.
insert into public.koja_world_services
(country_code,country_name,service_name,category,description,url,access_mode,is_active,is_verified)
select 'ZM','Zambia','HELSB','Loans & Finance',
'Higher Education Loans and Scholarships Board — student loans, scholarships and related public information.',
'https://www.helsb.gov.zm/','embed_or_external',true,true
where not exists (
  select 1 from public.koja_world_services
  where country_code='ZM' and service_name='HELSB'
);

insert into public.koja_world_services
(country_code,country_name,service_name,category,description,url,access_mode,is_active,is_verified)
select 'ZM','Zambia','Zanaco','Banking',
'Zambia National Commercial Bank public website and access point to its online banking and public services.',
'https://www.zanaco.co.zm/','embed_or_external',true,true
where not exists (
  select 1 from public.koja_world_services
  where country_code='ZM' and service_name='Zanaco'
);

insert into public.koja_world_services
(country_code,country_name,service_name,category,description,url,access_mode,is_active,is_verified)
select 'GH','Ghana','Ghana.GOV','Government',
'Official Ghana government digital services and payments platform.',
'https://www.ghana.gov.gh/','embed_or_external',true,true
where not exists (
  select 1 from public.koja_world_services
  where country_code='GH' and service_name='Ghana.GOV'
);

insert into public.koja_world_services
(country_code,country_name,service_name,category,description,url,access_mode,is_active,is_verified)
select 'NG','Nigeria','Nigeria e-Government Services','Government',
'Official Nigerian e-government gateway for public services.',
'https://services.gov.ng/services','embed_or_external',true,true
where not exists (
  select 1 from public.koja_world_services
  where country_code='NG' and service_name='Nigeria e-Government Services'
);

insert into public.koja_world_services
(country_code,country_name,service_name,category,description,url,access_mode,is_active,is_verified)
select 'ZA','South Africa','South African Government Services','Government',
'Official South African Government services directory and online-service entry points.',
'https://www.gov.za/services','embed_or_external',true,true
where not exists (
  select 1 from public.koja_world_services
  where country_code='ZA' and service_name='South African Government Services'
);
