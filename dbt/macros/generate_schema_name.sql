{#
  Usa el esquema configurado (BRONZE, SILVER, GOLD) tal cual, sin prefijarlo con el esquema del target.
  Asi las capas quedan como PSET2_ROSSMANN.BRONZE / .SILVER / .GOLD.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema | trim }}
    {%- else -%}
        {{ custom_schema_name | trim | upper }}
    {%- endif -%}
{%- endmacro %}
