{# Bronze: todos los snapshots de test.csv (dias a pronosticar), tipados. #}
with src as (
    select * from {{ source('raw', 'test') }}
)

select
    try_to_number(id)                             as test_id,
    try_to_number(store)                          as store_id,
    try_to_number(day_of_week)                    as day_of_week_src,
    try_to_date(record_date, 'YYYY-MM-DD')        as sales_date,
    try_to_number(open_flag)                      as open_flag,
    try_to_number(promo)                          as promo_flag,
    lower(trim(state_holiday))                    as state_holiday_code,
    try_to_number(school_holiday)                 as school_holiday_flag,
    _source_file,
    _source_row,
    _batch_id,
    _loaded_at
from src
