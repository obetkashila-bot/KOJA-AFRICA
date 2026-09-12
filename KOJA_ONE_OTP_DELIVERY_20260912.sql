-- KOJA ONE-OTP DELIVERY
-- Additive/update-safe. No table recreation.
-- One 6-digit order OTP is used for seller handover and buyer delivery confirmation.

alter table public.deliveries
  add column if not exists delivery_confirmation_code text,
  add column if not exists delivery_confirmation_verified boolean not null default false,
  add column if not exists delivery_confirmation_verified_at timestamptz,
  add column if not exists delivery_confirmation_attempts integer not null default 0,
  add column if not exists delivery_confirmation_locked boolean not null default false,
  add column if not exists seller_pickup_otp text,
  add column if not exists seller_pickup_otp_verified boolean not null default false,
  add column if not exists seller_pickup_otp_verified_at timestamptz,
  add column if not exists seller_pickup_otp_attempts integer not null default 0,
  add column if not exists seller_pickup_otp_locked boolean not null default false;

-- Synchronize active/unfinished deliveries to the single OTP.
update public.deliveries
set seller_pickup_otp = delivery_confirmation_code
where delivery_confirmation_code is not null
  and coalesce(status,'') not in ('completed','cancelled')
  and coalesce(pickup_verified,false) = false;

update public.deliveries set delivery_confirmation_attempts = 0 where delivery_confirmation_attempts is null;
update public.deliveries set delivery_confirmation_locked = false where delivery_confirmation_locked is null;
update public.deliveries set seller_pickup_otp_attempts = 0 where seller_pickup_otp_attempts is null;
update public.deliveries set seller_pickup_otp_locked = false where seller_pickup_otp_locked is null;

create index if not exists idx_koja_deliveries_one_otp
on public.deliveries (tracking_code, delivery_confirmation_verified, pickup_verified);

create unique index if not exists uq_koja_delivery_confirmation_code
on public.deliveries (delivery_confirmation_code)
where delivery_confirmation_code is not null;

-- Verification: unfinished deliveries should have the same value in both fields.
select tracking_code, status, pickup_verified, delivery_confirmation_verified,
       (delivery_confirmation_code = seller_pickup_otp) as same_otp
from public.deliveries
where created_at > now() - interval '30 days'
order by created_at desc
limit 50;
