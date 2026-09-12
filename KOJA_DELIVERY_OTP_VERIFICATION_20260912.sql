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

-- KOJA SELLER HANDOVER OTP
-- Seller-side handover is also server-verified in KOJA before pickup becomes valid.
alter table public.deliveries
  add column if not exists seller_pickup_otp text,
  add column if not exists seller_pickup_otp_verified boolean not null default false,
  add column if not exists seller_pickup_otp_verified_at timestamptz,
  add column if not exists seller_pickup_otp_attempts integer not null default 0,
  add column if not exists seller_pickup_otp_locked boolean not null default false;

create index if not exists idx_koja_deliveries_seller_pickup_otp
  on public.deliveries (tracking_code, seller_pickup_otp_verified, seller_pickup_otp_locked);

update public.deliveries
set seller_pickup_otp_attempts = 0 where seller_pickup_otp_attempts is null;
update public.deliveries
set seller_pickup_otp_verified = false where seller_pickup_otp_verified is null;
update public.deliveries
set seller_pickup_otp_locked = false where seller_pickup_otp_locked is null;

select tracking_code, sender_id, seller_pickup_otp_verified, seller_pickup_otp_attempts,
       seller_pickup_otp_locked, pickup_verified, status
from public.deliveries
order by created_at desc limit 20;
