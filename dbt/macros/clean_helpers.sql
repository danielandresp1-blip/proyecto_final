{# Convierte la etiqueta de PromoInterval en la lista de meses (texto '1,4,7,10'). Normaliza 'Sept' -> 'Sep'. #}
{% macro promo_interval_to_months(col) -%}
    case replace(trim({{ col }}), 'Sept', 'Sep')
        when 'Jan,Apr,Jul,Oct' then '1,4,7,10'
        when 'Feb,May,Aug,Nov' then '2,5,8,11'
        when 'Mar,Jun,Sep,Dec' then '3,6,9,12'
    end
{%- endmacro %}


{# Lunes de la semana ISO (anio, semana). El 4 de enero siempre cae en la semana ISO 1. #}
{% macro iso_week_start(year_col, week_col) -%}
    dateadd(
        day,
        ({{ week_col }} - 1) * 7 - (dayofweekiso(date_from_parts({{ year_col }}, 1, 4)) - 1),
        date_from_parts({{ year_col }}, 1, 4)
    )
{%- endmacro %}


{# Codigo de feriado estatal -> etiqueta legible #}
{% macro state_holiday_label(col) -%}
    case {{ col }}
        when '0' then 'none'
        when 'a' then 'public'
        when 'b' then 'easter'
        when 'c' then 'christmas'
    end
{%- endmacro %}


{# Clave de dim_holiday: 1..8, deterministica a partir del codigo y la bandera escolar #}
{% macro holiday_key(code_col, school_col) -%}
    (case {{ code_col }} when '0' then 0 when 'a' then 1 when 'b' then 2 when 'c' then 3 end) * 2
    + iff({{ school_col }}, 1, 0) + 1
{%- endmacro %}
