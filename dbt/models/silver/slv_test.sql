{#
  Silver - dias a pronosticar (test.csv). Una fila por tienda y dia; se usara en la etapa de scoring.

  Decision: Open nulo (11 filas, todas de la tienda 622). Se imputa Open = 1 y se marca is_open_imputed:
  son dias laborables sin feriado y la metrica de Kaggle ignora dias cerrados, asi que asumir "cerrada"
  descartaria predicciones necesarias; asumir "abierta" solo cuesta una prediccion de mas.
#}
with latest_batch as (
    select max(_loaded_at) as max_loaded_at from {{ ref('brz_test') }}
)

select
    t.test_id,
    t.store_id,
    t.sales_date,
    dayofweekiso(t.sales_date)                                as day_of_week,
    coalesce(t.open_flag, 1) = 1                              as is_open,
    t.open_flag is null                                       as is_open_imputed,
    t.promo_flag = 1                                          as is_promo,
    t.state_holiday_code,
    {{ state_holiday_label('t.state_holiday_code') }}         as state_holiday_type,
    t.school_holiday_flag = 1                                 as is_school_holiday,
    t._loaded_at
from {{ ref('brz_test') }} t
join latest_batch l on t._loaded_at = l.max_loaded_at
where t.test_id is not null
