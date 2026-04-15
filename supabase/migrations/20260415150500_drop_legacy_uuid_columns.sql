alter table public.price_snapshots
    drop constraint if exists price_snapshots_watching_product_id_fkey;

alter table public.price_snapshots
    drop column if exists legacy_watching_product_id;

alter table public.price_snapshots
    drop column if exists legacy_int_id;

alter table public.watched_products
    drop column if exists legacy_int_id;

alter table public.price_snapshots
    add constraint price_snapshots_watching_product_id_fkey
    foreign key (watching_product_id) references public.watched_products(id) on delete cascade;

create index if not exists idx_price_snapshots_watch_observed_at
    on public.price_snapshots (watching_product_id, observed_at);
