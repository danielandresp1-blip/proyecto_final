{{ config(severity = 'warn') }}
-- Completitud diaria: cada dia historico deberia tener al menos var('min_stores_per_day') tiendas.
-- Un dia por debajo suele indicar una ventana de ingesta incompleta.
select sales_date, count(*) as n_stores
from {{ ref('slv_sales_daily') }}
group by sales_date
having count(*) < {{ var('min_stores_per_day') }}
