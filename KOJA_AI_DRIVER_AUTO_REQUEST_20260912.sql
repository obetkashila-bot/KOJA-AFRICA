-- KOJA automatic driver request at Market checkout
-- Additive only. No table recreation or destructive changes.

alter table public.koja_market_orders
  add column if not exists auto_driver_request boolean not null default true;

create index if not exists idx_koja_market_orders_auto_driver_request
  on public.koja_market_orders (auto_driver_request, status, created_at desc);

select order_number, status, auto_driver_request, created_at
from public.koja_market_orders
order by created_at desc
limit 20;
