{#
  Silver - tiendas (staging limpio). Una fila por tienda.

  Decisiones de limpieza:
  1. Duplicados: RAW.STORE recibe un snapshot completo en cada carga -> se conserva el snapshot mas reciente
     por tienda (_loaded_at), que representa el estado vigente.
  2. CompetitionDistance nulo (3 tiendas): se deja NULL ("desconocido" no es lo mismo que 0 m ni que infinito);
     se marca has_competition_distance. La imputacion se decide en el modelado (PSet siguiente).
  3. CompetitionOpenSince nulo (~32% de tiendas): no se inventa una fecha. competition_open_since_date queda NULL.
  4. CompetitionOpenSinceYear < var('min_competition_year') (p. ej. 1900): valor centinela, anterior a la
     fundacion de Rossmann (1972) -> se anula la fecha y se marca is_competition_date_invalid.
  5. Promo2: los campos Promo2Since*/PromoInterval son nulos cuando Promo2 = 0 (nulos estructurales,
     no faltantes). Se valida esa consistencia con un test y se derivan promo2_since_date y los meses del ciclo.
  6. PromoInterval usa 'Sept' en lugar de 'Sep': se normaliza al convertir el texto a meses.
#}
with latest as (
    select *
    from {{ ref('brz_store') }}
    where store_id is not null
    qualify row_number() over (partition by store_id order by _loaded_at desc, _source_row) = 1
),

cleaned as (
    select
        store_id,
        store_type,
        assortment,
        case assortment
            when 'a' then 'basic'
            when 'b' then 'extra'
            when 'c' then 'extended'
        end                                                       as assortment_label,

        competition_distance_m,
        competition_distance_m is not null                        as has_competition_distance,

        competition_open_since_month,
        competition_open_since_year,
        coalesce(
            competition_open_since_year < {{ var('min_competition_year') }}
            or competition_open_since_month not between 1 and 12,
            false
        )                                                         as is_competition_date_invalid,

        promo2_flag = 1                                           as participates_promo2,
        iff(promo2_flag = 1, promo2_since_week, null)             as promo2_since_week,
        iff(promo2_flag = 1, promo2_since_year, null)             as promo2_since_year,
        iff(promo2_flag = 1, promo_interval_raw, null)            as promo2_interval_label,
        iff(promo2_flag = 1, {{ promo_interval_to_months('promo_interval_raw') }}, null)
                                                                  as promo2_interval_months,
        _batch_id,
        _loaded_at
    from latest
)

select
    *,
    case
        when competition_open_since_year is null or is_competition_date_invalid then null
        else date_from_parts(competition_open_since_year, competition_open_since_month, 1)
    end                                                           as competition_open_since_date,
    case
        when participates_promo2 and promo2_since_year is not null and promo2_since_week is not null
            then {{ iso_week_start('promo2_since_year', 'promo2_since_week') }}
    end                                                           as promo2_since_date
from cleaned
