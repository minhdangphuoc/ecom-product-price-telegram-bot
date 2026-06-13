-- Protect PostgREST-exposed tables. The bot uses a server-side database
-- connection, so enabling RLS blocks public access without affecting backend jobs.
alter table if exists public.telegram_users enable row level security;

alter table if exists public.watched_products enable row level security;

alter table if exists public.price_snapshots enable row level security;

alter table if exists public.discount_snapshots enable row level security;
