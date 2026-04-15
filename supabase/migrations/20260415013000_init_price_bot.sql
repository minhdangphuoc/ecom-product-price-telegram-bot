create extension if not exists pgcrypto;

create table if not exists public.telegram_users (
    telegram_user_id bigint primary key,
    chat_id bigint not null,
    username text,
    first_name text,
    last_name text,
    language_code text,
    is_bot boolean not null default false,
    timezone text not null default 'America/Los_Angeles',
    last_seen_at timestamptz not null default now(),
    last_daily_report_on date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.watched_products (
    id uuid primary key default gen_random_uuid(),
    telegram_user_id bigint not null references public.telegram_users(telegram_user_id) on delete cascade,
    name text not null,
    url text not null,
    vendor_id text not null,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (telegram_user_id, url)
);

create table if not exists public.price_snapshots (
    id uuid primary key default gen_random_uuid(),
    watching_product_id uuid not null references public.watched_products(id) on delete cascade,
    observed_at timestamptz not null default now(),
    product_name text not null,
    product_price numeric(12, 2) not null,
    currency text not null,
    in_stock boolean not null,
    article_number text,
    raw_payload text
);

create table if not exists public.discount_snapshots (
    id bigint primary key generated always as identity,
    vendor_id text not null,
    observed_on date not null,
    code text not null,
    condition text not null,
    source_url text not null,
    fingerprint text not null,
    created_at timestamptz not null default now(),
    unique (vendor_id, observed_on, code)
);

create index if not exists idx_watched_products_user_active
    on public.watched_products (telegram_user_id, active);

create index if not exists idx_price_snapshots_watch_observed_at
    on public.price_snapshots (watching_product_id, observed_at);

create index if not exists idx_discount_snapshots_observed_on_vendor
    on public.discount_snapshots (observed_on, vendor_id);
