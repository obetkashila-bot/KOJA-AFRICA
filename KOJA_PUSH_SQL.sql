create table if not exists public.koja_push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index if not exists koja_push_subscriptions_user_idx on public.koja_push_subscriptions(user_id);
