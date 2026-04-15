delete from public.discount_snapshots
where code is null
   or btrim(code) = '';

with ranked as (
    select
        id,
        row_number() over (
            partition by vendor_id, observed_on, code
            order by length(condition) desc, created_at asc, id asc
        ) as row_rank
    from public.discount_snapshots
)
delete from public.discount_snapshots d
using ranked r
where d.id = r.id
  and r.row_rank > 1;

alter table public.discount_snapshots
    alter column code set not null;

alter table public.discount_snapshots
    drop constraint if exists discount_snapshots_vendor_id_observed_on_fingerprint_key;

alter table public.discount_snapshots
    drop constraint if exists discount_snapshots_vendor_id_observed_on_code_key;

alter table public.discount_snapshots
    add constraint discount_snapshots_vendor_id_observed_on_code_key
    unique (vendor_id, observed_on, code);
