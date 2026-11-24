{#
  Dimension calendario. Grano: un dia. Cubre historico + horizonte de scoring (test.csv),
  de modo que tanto la tabla de hechos como el futuro set de prediccion tengan fecha conformada.
#}
with bounds as (
    select
        least(
            coalesce((select min(sales_date) from {{ ref('slv_sales_daily') }}), '{{ var("source_min_date") }}'::date),
            coalesce((select min(sales_date) from {{ ref('slv_test') }}), '{{ var("source_min_date") }}'::date)
        ) as min_date,
        greatest(
            coalesce((select max(sales_date) from {{ ref('slv_sales_daily') }}), '{{ var("source_max_date") }}'::date),
            coalesce((select max(sales_date) from {{ ref('slv_test') }}), '{{ var("scoring_max_date") }}'::date)
        ) as max_date
),

spine as (
    select dateadd(day, row_number() over (order by seq4()) - 1, b.min_date) as date_day, b.max_date
    from table(generator(rowcount => 5000))
    cross join bounds b
)

select
    to_number(to_char(date_day, 'YYYYMMDD'))  as date_key,
    date_day                                   as calendar_date,
    year(date_day)                             as year,
    quarter(date_day)                          as quarter,
    month(date_day)                            as month,
    monthname(date_day)                        as month_name_short,
    weekiso(date_day)                          as iso_week,
    yearofweekiso(date_day)                    as iso_year,
    day(date_day)                              as day_of_month,
    dayofyear(date_day)                        as day_of_year,
    dayofweekiso(date_day)                     as day_of_week_iso,
    dayname(date_day)                          as day_name_short,
    dayofweekiso(date_day) in (6, 7)           as is_weekend,
    date_day = date_trunc('month', date_day)   as is_month_start,
    date_day = last_day(date_day)              as is_month_end,
    datediff(day, '{{ var("source_min_date") }}'::date, date_day) as day_index
from spine
where date_day <= max_date
