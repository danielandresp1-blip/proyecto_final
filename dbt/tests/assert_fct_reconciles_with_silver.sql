-- Gold no debe perder ni inventar ventas respecto a Silver (filas y total de ventas).
with s as (
    select count(*) as n, sum(sales) as total_sales from {{ ref('slv_sales_daily') }}
),
f as (
    select count(*) as n, sum(sales) as total_sales from {{ ref('fct_sales_daily') }}
)
select s.n as n_silver, f.n as n_gold, s.total_sales as sales_silver, f.total_sales as sales_gold
from s cross join f
where s.n <> f.n or s.total_sales <> f.total_sales
