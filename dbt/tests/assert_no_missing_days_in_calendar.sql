-- dim_date debe ser continua: sin dias faltantes entre su minimo y su maximo.
with d as (
    select calendar_date,
           lag(calendar_date) over (order by calendar_date) as prev_date
    from {{ ref('dim_date') }}
)
select * from d
where prev_date is not null and datediff(day, prev_date, calendar_date) <> 1
