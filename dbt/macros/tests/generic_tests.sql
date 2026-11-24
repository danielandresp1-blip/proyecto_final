{#
  Tests genericos propios (sin dependencias externas para que dbt build no necesite red).
  Cada test devuelve las filas que violan la regla; 0 filas = test aprobado.
#}

{% test unique_combination_of_columns(model, combination_of_columns) %}
    select {{ combination_of_columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ combination_of_columns | join(', ') }}
    having count(*) > 1
{% endtest %}


{% test accepted_range(model, column_name, min_value=none, max_value=none, row_condition=none) %}
    select *
    from {{ model }}
    where {{ column_name }} is not null
      {% if row_condition %} and ({{ row_condition }}) {% endif %}
      and (
            false
            {% if min_value is not none %} or {{ column_name }} < {{ min_value }} {% endif %}
            {% if max_value is not none %} or {{ column_name }} > {{ max_value }} {% endif %}
          )
{% endtest %}


{% test expression_is_true(model, expression, row_condition=none) %}
    select *
    from {{ model }}
    where not ({{ expression }})
      {% if row_condition %} and ({{ row_condition }}) {% endif %}
{% endtest %}


{% test row_count_equals(model, compare_model) %}
    with a as (select count(*) as n from {{ model }}),
         b as (select count(*) as n from {{ compare_model }})
    select a.n as n_model, b.n as n_compare
    from a cross join b
    where a.n <> b.n
{% endtest %}
