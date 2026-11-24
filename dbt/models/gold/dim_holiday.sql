{#
  Dimension "junk" de contexto festivo: combinacion de feriado estatal x vacaciones escolares.
  Se generan todas las combinaciones validas (4 x 2 = 8 filas) para que cualquier fila del hecho
  encuentre su clave, aunque una combinacion aun no aparezca en los datos.
#}
with state_holiday as (
    select column1 as state_holiday_code, column2 as state_holiday_type
    from values ('0', 'none'), ('a', 'public'), ('b', 'easter'), ('c', 'christmas')
),

school_holiday as (
    select column1 as is_school_holiday
    from values (false), (true)
)

select
    {{ holiday_key('s.state_holiday_code', 'h.is_school_holiday') }} as holiday_key,
    s.state_holiday_code,
    s.state_holiday_type,
    s.state_holiday_code <> '0'                                      as is_state_holiday,
    h.is_school_holiday,
    s.state_holiday_code <> '0' or h.is_school_holiday               as is_any_holiday
from state_holiday s
cross join school_holiday h
