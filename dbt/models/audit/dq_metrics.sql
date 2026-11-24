{#
  Evidencia de calidad de datos. Cada fila es una metrica: problema, capa, numerador, denominador y %.
  Es la fuente de las cifras del memo tecnico (seccion Data Quality).
#}
with
raw_train as (select * from {{ source('raw', 'train_sales') }}),
brz_train as (select * from {{ ref('brz_train_sales') }}),
brz_store as (select * from {{ ref('brz_store') }}),
store_latest as (select * from {{ ref('slv_store') }}),
sales as (select * from {{ ref('slv_sales_daily') }}),
brz_test as (
    select * from {{ ref('brz_test') }}
    qualify _loaded_at = max(_loaded_at) over ()
),

stores_x_days as (
    select (select count(distinct store_id) from sales)
         * (select datediff(day, min(sales_date), max(sales_date)) + 1 from sales) as n
),

metrics as (
    -- Completitud
    select 'completitud' as dimension, 'train: tienda-dias faltantes vs. calendario completo' as metric, 'SILVER' as layer,
           (select n from stores_x_days) - (select count(*) from sales) as numerator,
           (select n from stores_x_days) as denominator
    union all
    select 'completitud', 'train: tiendas con dias faltantes', 'GOLD',
           (select count_if(has_data_gap) from {{ ref('dim_store') }}), (select count(*) from {{ ref('dim_store') }})
    union all
    select 'completitud', 'store: CompetitionDistance nulo', 'SILVER',
           count_if(competition_distance_m is null), count(*) from store_latest
    union all
    select 'completitud', 'store: CompetitionOpenSince nulo', 'SILVER',
           count_if(competition_open_since_year is null), count(*) from store_latest
    union all
    select 'completitud', 'store: campos Promo2 nulos (estructural, Promo2 = 0)', 'SILVER',
           count_if(not participates_promo2), count(*) from store_latest
    union all
    select 'completitud', 'test: Open nulo', 'BRONZE',
           count_if(open_flag is null), count(*) from brz_test

    -- Validez
    union all
    select 'validez', 'train: valores no convertibles a tipo', 'BRONZE',
           count_if(_has_cast_error), count(*) from brz_train
    union all
    select 'validez', 'store: anio de competencia centinela (< min_competition_year)', 'SILVER',
           count_if(is_competition_date_invalid), count(*) from store_latest
    union all
    select 'validez', 'train: ventas o clientes negativos', 'SILVER',
           count_if(sales < 0 or customers < 0), count(*) from sales

    -- Consistencia
    union all
    select 'consistencia', 'train: DayOfWeek no coincide con la fecha', 'SILVER',
           count_if(is_dow_mismatch), count(*) from sales
    union all
    select 'consistencia', 'train: tienda cerrada con ventas > 0', 'SILVER',
           count_if(is_closed_with_sales), count(*) from sales
    union all
    select 'consistencia', 'store: PromoInterval con abreviatura no estandar (Sept)', 'BRONZE',
           count_if(promo_interval_raw ilike '%Sept%'), count(*) from brz_store
           where _loaded_at = (select max(_loaded_at) from brz_store)

    -- Precision / plausibilidad
    union all
    select 'precision', 'train: tienda abierta con ventas = 0', 'SILVER',
           count_if(is_open_zero_sales), count_if(is_open) from sales
    union all
    select 'precision', 'train: ventas > 0 sin clientes', 'SILVER',
           count_if(is_sales_without_customers), count_if(sales > 0) from sales
    union all
    select 'precision', 'train: ticket promedio fuera de [1, 100] EUR', 'SILVER',
           count_if(sales_per_customer not between 1 and 100), count_if(sales_per_customer is not null) from sales

    -- Distribucion relevante para el negocio
    union all
    select 'cobertura', 'train: dias de tienda cerrada (Open = 0)', 'SILVER',
           count_if(not is_open), count(*) from sales

    -- Unicidad
    union all
    select 'unicidad', 'raw train: filas duplicadas (tienda, fecha)', 'RAW',
           (select count(*) - count(distinct store, record_date) from raw_train), (select count(*) from raw_train)
    union all
    select 'unicidad', 'raw store: filas repetidas por snapshots acumulados', 'BRONZE',
           count(*) - count(distinct store_id), count(*) from brz_store
)

select
    dimension,
    metric,
    layer,
    numerator,
    denominator,
    round(100 * numerator / nullif(denominator, 0), 2) as pct,
    current_timestamp()                                as computed_at
from metrics
