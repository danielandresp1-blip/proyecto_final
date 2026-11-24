{{
  config(
    materialized = 'incremental',
    unique_key = 'sales_key',
    incremental_strategy = 'merge',
    on_schema_change = 'append_new_columns',
    cluster_by = ['date_key']
  )
}}
{#
  Tabla de hechos de ventas.
  GRANO: una fila por tienda y dia calendario OBSERVADO en la fuente (store_id, sales_date).
  Medidas aditivas: sales, customers. Medida no aditiva: sales_per_customer.
  Atributos que dependen de la fecha (promo2 activa, competencia abierta) se calculan aqui, porque cambian
  dia a dia para una misma tienda y no pueden vivir en dim_store.
  Incremental: reprocesa las filas cargadas desde (max _loaded_at - lookback), para absorber recargas de Raw.
#}
with sales as (
    select *
    from {{ ref('slv_sales_daily') }}
    {% if is_incremental() %}
    where _loaded_at >= (
        select dateadd(day, -{{ var('incremental_lookback_days') }}, coalesce(max(_loaded_at), '1900-01-01'::timestamp_ntz))
        from {{ this }}
    )
    {% endif %}
),

store as (
    select * from {{ ref('slv_store') }}
)

select
    md5(s.store_id || '|' || to_char(s.sales_date, 'YYYY-MM-DD'))   as sales_key,
    s.store_id                                                      as store_key,
    to_number(to_char(s.sales_date, 'YYYYMMDD'))                    as date_key,
    {{ holiday_key('s.state_holiday_code', 's.is_school_holiday') }} as holiday_key,

    -- medidas
    s.sales,
    s.customers,
    s.sales_per_customer,

    -- banderas operativas del dia
    s.is_open,
    s.is_promo,

    -- Promo2 activa: la tienda participa, ya empezo y el mes esta en su ciclo
    coalesce(
        st.participates_promo2
        and s.sales_date >= st.promo2_since_date
        and contains(',' || st.promo2_interval_months || ',', ',' || month(s.sales_date)::varchar || ','),
        false
    )                                                               as is_promo2_active,
    case
        when st.competition_distance_m is null              then 'no_info'
        when st.competition_open_since_date is null         then 'unknown_since'
        when s.sales_date >= st.competition_open_since_date then 'open'
        else 'not_yet_open'
    end                                                             as competition_status,
    iff(s.sales_date >= st.competition_open_since_date,
        datediff(month, st.competition_open_since_date, s.sales_date), null) as months_since_competition_open,
    iff(s.sales_date >= st.promo2_since_date,
        datediff(week, st.promo2_since_date, s.sales_date), null)  as weeks_since_promo2_start,

    -- calidad / elegibilidad para el modelo
    s.is_open_zero_sales,
    s.is_sales_without_customers,
    s.is_model_eligible,

    s._batch_id,
    s._loaded_at
from sales s
left join store st on s.store_id = st.store_id
