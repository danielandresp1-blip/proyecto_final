{#
  Silver - ventas diarias limpias. Grano: una fila por tienda y dia observado.

  Decisiones de limpieza:
  1. Claves invalidas: se descartan filas sin store_id o sin fecha valida (no se pueden ubicar en el grano).
  2. Duplicados (store_id, sales_date): pueden aparecer si una ventana se recargo fuera de la transaccion.
     Se conserva la carga mas reciente (_loaded_at), que refleja la ultima version de la fuente.
  3. DayOfWeek: se recalcula desde la fecha (ISO, 1 = lunes) y se marca si la fuente no coincidia.
  4. StateHoliday: el codigo ('0','a','b','c') se normaliza y se traduce a etiqueta legible.
  5. Tiendas cerradas (Open = 0, ~17%): se CONSERVAN. Son parte del grano tienda-dia y explican las ventas 0;
     se marca is_model_eligible = FALSE para que el modelo pueda excluirlas.
  6. Abierta con ventas 0 (54 filas): dato anomalo (posible cierre no registrado). Se conserva y se marca
     is_open_zero_sales; queda fuera de is_model_eligible.
  7. No se imputan los dias faltantes (hueco de 180 tiendas en 2014-S2): inventar ventas sesgaria el modelo.
     El hueco se documenta en dim_store (cobertura) y se maneja con ventanas por fecha en Spark.
#}
with base as (
    select *
    from {{ ref('brz_train_sales') }}
    where store_id is not null
      and sales_date is not null
    qualify row_number() over (
        partition by store_id, sales_date
        order by _loaded_at desc, _source_row desc
    ) = 1
)

select
    store_id,
    sales_date,
    dayofweekiso(sales_date)                                  as day_of_week,
    coalesce(day_of_week_src <> dayofweekiso(sales_date), true) as is_dow_mismatch,

    sales,
    customers,
    open_flag = 1                                             as is_open,
    promo_flag = 1                                            as is_promo,
    state_holiday_code,
    {{ state_holiday_label('state_holiday_code') }}           as state_holiday_type,
    school_holiday_flag = 1                                   as is_school_holiday,

    iff(customers > 0, round(sales / customers, 4), null)     as sales_per_customer,

    (open_flag = 0 and sales > 0)                             as is_closed_with_sales,
    (open_flag = 1 and sales = 0)                             as is_open_zero_sales,
    (sales > 0 and coalesce(customers, 0) = 0)                as is_sales_without_customers,

    (open_flag = 1 and sales > 0)                             as is_model_eligible,

    _batch_id,
    _loaded_at
from base
