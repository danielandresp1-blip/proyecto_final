{# Bronze: todos los snapshots de store.csv, tipados. La deduplicacion ocurre en Silver. #}
with src as (
    select * from {{ source('raw', 'store') }}
)

select
    try_to_number(store)                          as store_id,
    lower(trim(store_type))                       as store_type,
    lower(trim(assortment))                       as assortment,
    try_to_number(competition_distance)           as competition_distance_m,
    try_to_number(competition_open_since_month)   as competition_open_since_month,
    try_to_number(competition_open_since_year)    as competition_open_since_year,
    try_to_number(promo2)                         as promo2_flag,
    try_to_number(promo2_since_week)              as promo2_since_week,
    try_to_number(promo2_since_year)              as promo2_since_year,
    nullif(trim(promo_interval), '')              as promo_interval_raw,
    _source_file,
    _source_row,
    _batch_id,
    _loaded_at
from src
