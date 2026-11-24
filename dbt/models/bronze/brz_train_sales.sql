{#
  Bronze: copia 1:1 de RAW.TRAIN_SALES con tipos de datos.
  No filtra, no deduplica y no corrige: cualquier valor que no se pueda convertir queda NULL y se marca
  con _has_cast_error para medirlo en la auditoria de calidad.
#}
with src as (
    select * from {{ source('raw', 'train_sales') }}
)

select
    try_to_number(store)                          as store_id,
    try_to_number(day_of_week)                    as day_of_week_src,
    try_to_date(record_date, 'YYYY-MM-DD')        as sales_date,
    try_to_number(sales)                          as sales,
    try_to_number(customers)                      as customers,
    try_to_number(open_flag)                      as open_flag,
    try_to_number(promo)                          as promo_flag,
    lower(trim(state_holiday))                    as state_holiday_code,
    try_to_number(school_holiday)                 as school_holiday_flag,

    (   (store is not null and try_to_number(store) is null)
     or (record_date is not null and try_to_date(record_date, 'YYYY-MM-DD') is null)
     or (sales is not null and try_to_number(sales) is null)
     or (customers is not null and try_to_number(customers) is null)
     or (open_flag is not null and try_to_number(open_flag) is null)
    )                                             as _has_cast_error,

    _source_file,
    _source_row,
    _batch_id,
    _loaded_at
from src
