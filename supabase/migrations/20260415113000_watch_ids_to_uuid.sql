create extension if not exists pgcrypto;

alter table public.watched_products
    add column if not exists uuid_id uuid default gen_random_uuid();

update public.watched_products
set uuid_id = gen_random_uuid()
where uuid_id is null;

alter table public.watched_products
    alter column uuid_id set not null;

alter table public.price_snapshots
    add column if not exists watching_product_uuid uuid;

update public.price_snapshots s
set watching_product_uuid = w.uuid_id
from public.watched_products w
where s.watching_product_uuid is null
  and s.watching_product_id = w.id;

alter table public.price_snapshots
    alter column watching_product_uuid set not null;

alter table public.price_snapshots
    drop constraint if exists price_snapshots_watching_product_id_fkey;

alter table public.watched_products
    drop constraint if exists watched_products_pkey;

drop index if exists public.idx_price_snapshots_watch_observed_at;

do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'watched_products'
          and column_name = 'id'
          and data_type <> 'uuid'
    ) then
        alter table public.watched_products rename column id to legacy_int_id;
    end if;

    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'watched_products'
          and column_name = 'uuid_id'
    ) then
        alter table public.watched_products rename column uuid_id to id;
    end if;

    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'price_snapshots'
          and column_name = 'watching_product_id'
          and data_type <> 'uuid'
    ) then
        alter table public.price_snapshots rename column watching_product_id to legacy_watching_product_id;
    end if;

    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'price_snapshots'
          and column_name = 'watching_product_uuid'
    ) then
        alter table public.price_snapshots rename column watching_product_uuid to watching_product_id;
    end if;
end $$;

alter table public.watched_products
    add constraint watched_products_pkey primary key (id);

alter table public.price_snapshots
    add constraint price_snapshots_watching_product_id_fkey
    foreign key (watching_product_id) references public.watched_products(id) on delete cascade;

create index if not exists idx_price_snapshots_watch_observed_at
    on public.price_snapshots (watching_product_id, observed_at);
