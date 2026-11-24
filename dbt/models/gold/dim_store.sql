{#
  Dimension tienda (SCD tipo 1: la fuente solo entrega el estado vigente, no historia de cambios).
  Agrega metricas de cobertura para que el hueco de 2014-S2 quede visible para el modelado.
#}
with coverage as (
    select
        store_id,
        min(sales_date)                    as first_sales_date,
        max(sales_date)                    as last_sales_date,
        count(*)                           as n_days_observed,
        count_if(is_open)                  as n_days_open
    from {{ ref('slv_sales_daily') }}
    group by store_id
),

expected as (
    select datediff(day, min(sales_date), max(sales_date)) + 1 as n_days_expected
    from {{ ref('slv_sales_daily') }}
)

select
    s.store_id                                             as store_key,
    s.store_id,
    s.store_type,
    s.assortment,
    s.assortment_label,
    s.competition_distance_m,
    s.has_competition_distance,
    s.competition_open_since_date,
    s.is_competition_date_invalid,
    s.participates_promo2,
    s.promo2_since_date,
    s.promo2_interval_label,
    s.promo2_interval_months,
    c.first_sales_date,
    c.last_sales_date,
    coalesce(c.n_days_observed, 0)                         as n_days_observed,
    coalesce(c.n_days_open, 0)                             as n_days_open,
    round(coalesce(c.n_days_observed, 0) / nullif(e.n_days_expected, 0), 4) as coverage_ratio,
    coalesce(c.n_days_observed, 0) < e.n_days_expected     as has_data_gap
from {{ ref('slv_store') }} s
left join coverage c on s.store_id = c.store_id
cross join expected e
