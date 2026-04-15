create extension if not exists pgcrypto;

alter table public.price_snapshots
    add column if not exists uuid_id uuid default gen_random_uuid();

update public.price_snapshots
set uuid_id = gen_random_uuid()
where uuid_id is null;

alter table public.price_snapshots
    alter column uuid_id set not null;

alter table public.price_snapshots
    drop constraint if exists price_snapshots_pkey;

do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'price_snapshots'
          and column_name = 'id'
          and data_type <> 'uuid'
    ) then
        alter table public.price_snapshots rename column id to legacy_int_id;
    end if;

    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'public'
          and table_name = 'price_snapshots'
          and column_name = 'uuid_id'
    ) then
        alter table public.price_snapshots rename column uuid_id to id;
    end if;
end $$;

alter table public.price_snapshots
    add constraint price_snapshots_pkey primary key (id);
